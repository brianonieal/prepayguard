#!/usr/bin/env python3
"""Ingest the REAL SAM.gov exclusions (federal debarment list) into the versioned
reference store, alongside the three synthetic restricted sources (Work Order 2).

Source: GSA System for Award Management (SAM.gov) Exclusions API v4
  https://api.sam.gov/entity-information/v4/exclusions
Access (verified 2026-07-06, see docs/sme/REAL_SOURCE_INGEST.md): requires a
SAM.gov account + API key. The key is NEVER hard-coded or committed; it is read
from the SAM_API_KEY environment variable (in production it belongs in Secrets
Manager, same discipline as the DEC-7 webhook secret).

This reuses the v2.1.0 versioned reference-store LIFECYCLE (DEC-18): it claims the
next version number with an S3 conditional put on reference/versions/{N}.json and
repoints reference/current.json, exactly like console_api._put_reference and the
seed_reference_data.py bulk seed. It does NOT bolt on a second store.

Real-world messiness handled (course objective 10) is documented inline and in
docs/sme/REAL_SOURCE_INGEST.md: SAM has no TIN (name-based matching only; UEI kept
for provenance), classification variety (Firm / Individual / Vessel / Special
Entity), exclusion-type variety mapped to severity, active-only filtering, and a
deliberate size cap so the in-store cosine design (DEC-19, scoped to hundreds of
entries) and its publish-time embedding cost stay bounded.

Usage:
  SAM_API_KEY=... python scripts/ingest_sam_exclusions.py --bucket treasury-dev-reference-<ACCOUNT_ID> [--limit 300] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import boto3
from botocore.exceptions import ClientError

DEFAULT_ENDPOINT = "https://api.sam.gov/entity-information/v4/exclusions"
EMBED_MODEL = "amazon.titan-embed-text-v2:0"
CURRENT_KEY = "reference/current.json"
SAM_SOURCE = "sam_exclusions"

# exclusionType / classification -> severity. Completed debarments and prohibitions
# are the strongest signal; pending proceedings and voluntary exclusions are a step
# down but still route a payment to a human. Documented mapping, not a guess buried
# in code (objective 10).
# Keys are the REAL SAM v4 exclusionType strings (verified against the live API
# 2026-07-06; note "Complete", not "Completed").
SEVERITY_BY_EXCLUSION_TYPE = {
    "Prohibition/Restriction": "high",
    "Ineligible (Proceedings Complete)": "high",
    "Ineligible (Proceedings Pending)": "medium",
    "Voluntary Exclusion": "medium",
}


# ---- fetch (real GSA API) ---------------------------------------------------
#
# Verified against the live API 2026-07-06:
# - Send NO "Accept: application/json" header (that returns 406) and a neutral
#   User-Agent (the default urllib agent is blocked); then the endpoint returns 200.
# - The free/personal key tier is 10 requests/day and returns HTTP 429 with a
#   retry-after date once exhausted (resets 00:00 GMT). So the DEFAULT paginated
#   pull is deliberately capped to fit that budget (PAGE_SIZE=10 -> <=9 calls for
#   the default 90-record cap, leaving one call of margin). A higher-tier key or
#   the --extract mode lifts that.

PAGE_SIZE = 10  # v4 regular-endpoint max
FREE_TIER_DAILY_CALLS = 10


class RateLimited(RuntimeError):
    pass


def _get_json(url: str, timeout: int = 60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https host)
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RateLimited(f"429 Too Many Requests (retry-after: {exc.headers.get('retry-after')}). "
                              "Free tier is 10 requests/day and resets 00:00 GMT; lower --limit or use a "
                              "higher-tier key / --extract.") from exc
        raise


def fetch_exclusions(api_key: str, endpoint: str, limit: int) -> list[dict]:
    """Paginated pull of exclusions (size<=10 per the v4 contract), capped at `limit`
    so the embedded reference doc stays within the in-store-cosine budget AND within
    the free-tier daily call budget. Returns raw records; normalization is separate.
    Raises RateLimited (rather than hanging) when the daily quota is spent."""
    out: list[dict] = []
    page = 0
    while len(out) < limit and page <= 999:
        qs = urllib.parse.urlencode({"api_key": api_key, "page": page, "size": PAGE_SIZE})
        records = _records_from_payload(_get_json(f"{endpoint}?{qs}", timeout=60))
        if not records:
            break
        out.extend(records)
        page += 1
        time.sleep(0.2)  # be polite to the rate-limited API
    return out[:limit]


def fetch_exclusions_extract(api_key: str, endpoint: str, limit: int, poll_timeout: int = 240) -> list[dict]:
    """One-call extract path (for a higher-tier key or the full list). Requests
    format=json, which the v4 API generates asynchronously and exposes via a
    download token/URL; polls that URL until the file is ready, then caps locally.
    Written against the documented contract; the exact envelope is confirmed on the
    first real run (raw shape is logged), so treat this as validated-on-first-use."""
    qs = urllib.parse.urlencode({"api_key": api_key, "format": "json"})
    first = _get_json(f"{endpoint}?{qs}", timeout=90)
    # The generation response may already carry records, or a token / download URL.
    recs = _records_from_payload(first)
    if recs:
        return recs[:limit]
    token = first.get("token") or (first.get("_embedded") or {}).get("token")
    dl = first.get("downloadUrl") or first.get("link")
    if not (token or dl):
        raise RuntimeError(f"extract response had neither records nor a token/url; keys={list(first.keys())}")
    base = endpoint.rsplit("/", 1)[0] + "/download-exclusions"
    url = dl or f"{base}?{urllib.parse.urlencode({'api_key': api_key, 'token': token})}"
    waited = 0
    while waited <= poll_timeout:
        try:
            payload = _get_json(url, timeout=90)
        except urllib.error.HTTPError as exc:
            if exc.code in (202, 404):  # still generating
                time.sleep(10)
                waited += 10
                continue
            raise
        recs = _records_from_payload(payload) or (payload if isinstance(payload, list) else [])
        if recs:
            return recs[:limit]
        time.sleep(10)
        waited += 10
    raise TimeoutError(f"extract not ready after {poll_timeout}s")


def _records_from_payload(payload: dict) -> list[dict]:
    """The v4 response wraps records; tolerate the couple of shapes SAM has used."""
    for key in ("excludedEntity", "exclusionDetails", "results", "entityData"):
        v = payload.get(key)
        if isinstance(v, list):
            return v
    emb = payload.get("_embedded") or {}
    if isinstance(emb.get("results"), list):
        return emb["results"]
    return []


# ---- normalize (pure, unit-tested; no network, no Bedrock) ------------------

def _record_name(ident: dict) -> str:
    """SAM populates entityName for both firms and individuals; fall back to the
    assembled person-name parts (prefix/first/middle/last/suffix) for robustness."""
    v = ident.get("entityName")
    if isinstance(v, str) and v.strip():
        return v.strip()
    parts = [ident.get("prefix"), ident.get("firstName"), ident.get("middleName"),
             ident.get("lastName"), ident.get("suffix")]
    return " ".join(p.strip() for p in parts if isinstance(p, str) and p.strip()).strip()


def _is_active(raw: dict) -> bool:
    """Active when any action carries recordStatus 'Active'. The real v4 shape nests
    these under exclusionActions.listOfActions; a flat recordStatus is also accepted
    for schema-drift tolerance."""
    actions = (raw.get("exclusionActions") or {}).get("listOfActions") or []
    statuses = [str(a.get("recordStatus") or "").strip().lower() for a in actions]
    if statuses:
        return "active" in statuses
    flat = str(raw.get("recordStatus") or "").strip().lower()
    return flat == "active"  # no actions and no active status -> drop (conservative)


def normalize_record(raw: dict) -> dict | None:
    """Map one raw SAM v4 exclusion (nested exclusionDetails/exclusionIdentification/
    exclusionActions) to the reference-list schema, or None to drop it. SAM has NO
    TIN, so tin is empty and matching runs on name only (exact/fuzzy/semantic);
    ueiSAM is carried for audit provenance, not for matching."""
    if not _is_active(raw):
        return None
    ident = raw.get("exclusionIdentification") or {}
    details = raw.get("exclusionDetails") or {}
    name = _record_name(ident)
    if not name:
        return None
    exclusion_type = str(details.get("exclusionType") or "").strip()
    classification = str(details.get("classificationType") or "").strip()
    return {
        "name": name,
        "tin": "",  # SAM keys on name / UEI, never a TIN
        "uei": (ident.get("ueiSAM") or "").strip() or None,
        "source": SAM_SOURCE,
        "severity": SEVERITY_BY_EXCLUSION_TYPE.get(exclusion_type, "high"),
        "classification": classification or None,
        "exclusion_type": exclusion_type or None,
        "excluding_agency": (details.get("excludingAgencyName") or "").strip() or None,
    }


def normalize_all(raw_records: list[dict], normalizer=normalize_record) -> list[dict]:
    """Normalize with the given per-record normalizer, drop inactive/nameless, and
    dedupe on (normalized name, uei). Shared by the GSA and OpenSanctions sources."""
    seen: set = set()
    entries: list[dict] = []
    for raw in raw_records:
        e = normalizer(raw)
        if e is None:
            continue
        k = (e["name"].lower(), e["uei"])
        if k in seen:
            continue
        seen.add(k)
        entries.append(e)
    return entries


# ---- OpenSanctions source (keyless, no rate limit; CC-BY-NC) ----------------
#
# Same underlying GSA SAM data, republished daily as a bulk file. Verified reachable
# keyless 2026-07-06. targets.simple.csv columns:
#   id, schema, name, aliases, birth_date, countries, addresses, identifiers,
#   sanctions ("<program> - <status> - <date>", e.g. "Reciprocal - Active - ..."),
#   program_ids, dataset, first_seen, last_seen, last_change

OPENSANCTIONS_INDEX = "https://data.opensanctions.org/datasets/latest/us_sam_exclusions/index.json"
_OS_SCHEMA_TO_CLASS = {"Person": "Individual", "LegalEntity": "Entity",
                       "Company": "Entity", "Organization": "Entity"}


def fetch_opensanctions(limit: int) -> list[dict]:
    """Resolve the current targets.simple.csv from the latest dataset index, download
    it (keyless, no rate limit), and return raw CSV rows (dicts). Capped at `limit`."""
    index = _get_json(OPENSANCTIONS_INDEX, timeout=60)
    csv_url = next((r["url"] for r in index.get("resources", [])
                    if r.get("name") == "targets.simple.csv"), None)
    if not csv_url:
        raise RuntimeError("targets.simple.csv not found in the OpenSanctions dataset index")
    req = urllib.request.Request(csv_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310 (fixed https host)
        text = resp.read().decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    return rows[:limit] if limit else rows


def normalize_opensanctions_row(row: dict) -> dict | None:
    """Map one OpenSanctions CSV row to the reference schema. The `sanctions` field
    carries '<program> - <status> - <date>'; keep only Active rows. No TIN; the first
    UEI-like identifier is kept for provenance."""
    sanctions = str(row.get("sanctions") or "")
    # Each sanction is "<program> - <status> - <date>"; multiple are ';'-joined.
    # Match the STATUS token exactly ("Inactive" contains the substring "active").
    def _status(s):
        parts = [p.strip() for p in s.split(" - ")]
        return parts[1].lower() if len(parts) >= 2 else ""
    if not any(_status(s) == "active" for s in sanctions.split(";")):
        return None
    name = str(row.get("name") or "").strip()
    if not name:
        return None
    program = sanctions.split(" - ")[0].strip() if sanctions else ""
    ident = str(row.get("identifiers") or "").split(";")[0].strip()
    return {
        "name": name,
        "tin": "",
        "uei": ident or None,
        "source": SAM_SOURCE,
        "severity": "high",  # every SAM exclusion is a debarment/suspension signal
        "classification": _OS_SCHEMA_TO_CLASS.get(str(row.get("schema") or "").strip(), "Entity"),
        "exclusion_type": program or None,
        "excluding_agency": None,  # not carried in the simple CSV
    }


# ---- build the versioned doc (reuse the synthetic restricted sources) -------

def build_reference_doc(current_doc: dict, real_sam_entries: list[dict], embed_fn) -> dict:
    """Keep the three synthetic restricted sources (DMF, TOP, OIG LEIE) from the
    current live doc (reusing their existing embeddings), replace the synthetic
    sam_exclusions entries with the real GSA feed, and embed the real entries."""
    kept = []
    for e in current_doc.get("entries", []):
        if e.get("source") != SAM_SOURCE:  # carry non-SAM synthetic entries verbatim (+ their embeddings)
            kept.append(e)
    embedded_real = []
    for e in real_sam_entries:
        e = {**e, "embedding": embed_fn(e["name"]), "embedding_model": EMBED_MODEL}
        embedded_real.append(e)

    sources = dict(current_doc.get("sources", {}))
    sources[SAM_SOURCE] = ("SAM.gov exclusions (GSA System for Award Management) - REAL federal "
                           "debarment/suspension list, ingested via the v4 Exclusions API")
    return {
        "version": current_doc.get("version", 0) + 1,
        "updated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "updated_by": f"ingest_sam_exclusions.py (GSA SAM v4 real source; {len(embedded_real)} real, "
                      f"{len(kept)} synthetic restricted)",
        "sources": sources,
        "semantic_threshold": current_doc.get("semantic_threshold", 0.72),
        "entries": kept + embedded_real,
    }


# ---- publish (reuse the DEC-18 versioned lifecycle) -------------------------

def publish(s3, bucket: str, doc: dict) -> int:
    """Claim reference/versions/{N}.json with a conditional put (If-None-Match: *),
    then repoint reference/current.json. Mirrors console_api._put_reference so
    concurrent publishes can never mint the same immutable version."""
    n = doc["version"]
    body = json.dumps(doc, indent=2).encode()
    try:
        s3.put_object(Bucket=bucket, Key=f"reference/versions/{n}.json",
                      Body=body, ContentType="application/json", IfNoneMatch="*")
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("PreconditionFailed", "412"):
            sys.exit(f"version {n} already exists - another publish won the race; re-run to claim the next")
        raise
    s3.put_object(Bucket=bucket, Key=CURRENT_KEY, Body=body, ContentType="application/json")
    return n


def _titan_embed(bedrock):
    def embed(text: str) -> list[float]:
        r = bedrock.invoke_model(modelId=EMBED_MODEL,
                                 body=json.dumps({"inputText": str(text or ""), "normalize": True}),
                                 accept="application/json", contentType="application/json")
        return json.loads(r["body"].read())["embedding"]
    return embed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True, help="reference-store bucket, e.g. treasury-dev-reference-<acct>")
    ap.add_argument("--source", choices=["gsa", "opensanctions"], default="gsa",
                    help="gsa = authoritative SAM v4 API (needs SAM_API_KEY, rate-limited); "
                         "opensanctions = keyless bulk file of the same GSA data (no rate limit, CC-BY-NC).")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--limit", type=int, default=90,
                    help="cap on real SAM entries. Default 90 fits the free GSA 10/day tier (<=9 paginated calls) "
                         "and the in-store-cosine budget; raise it with --extract, opensanctions, or a paid key.")
    ap.add_argument("--extract", action="store_true",
                    help="GSA only: use the one-call async extract endpoint instead of paginating.")
    ap.add_argument("--dry-run", action="store_true", help="fetch + normalize + summarize, do NOT publish")
    args = ap.parse_args()

    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")
    s3 = boto3.client("s3", region_name="us-east-2")

    if args.source == "opensanctions":
        print(f"Fetching up to {args.limit} SAM exclusions via OpenSanctions (keyless bulk file) ...")
        raw = fetch_opensanctions(args.limit)
        normalizer = normalize_opensanctions_row
    else:
        api_key = os.environ.get("SAM_API_KEY")
        if not api_key:
            sys.exit("SAM_API_KEY is not set. Put a SAM.gov API key in .sam_api_key (gitignored) and export it, "
                     "or use --source opensanctions (keyless).")
        pages_needed = (args.limit + PAGE_SIZE - 1) // PAGE_SIZE
        if not args.extract and pages_needed > FREE_TIER_DAILY_CALLS:
            print(f"  WARNING: --limit {args.limit} needs {pages_needed} calls; the free tier allows "
                  f"{FREE_TIER_DAILY_CALLS}/day. Lower --limit, use --extract, or --source opensanctions.")
        mode = "extract (one call)" if args.extract else f"paginated ({pages_needed} calls)"
        print(f"Fetching up to {args.limit} SAM exclusions via GSA {mode} from {args.endpoint} ...")
        try:
            raw = (fetch_exclusions_extract if args.extract else fetch_exclusions)(api_key, args.endpoint, args.limit)
        except RateLimited as exc:
            sys.exit(f"RATE LIMITED: {exc}")
        normalizer = normalize_record

    if raw:
        print(f"  first raw record keys: {list(raw[0].keys())}")
    entries = normalize_all(raw, normalizer)
    print(f"  fetched {len(raw)} raw, {len(entries)} active+named+deduped")
    by_class: dict = {}
    for e in entries:
        by_class[e.get("classification") or "Unspecified"] = by_class.get(e.get("classification") or "Unspecified", 0) + 1
    print(f"  by classification: {by_class}")

    current = json.loads(s3.get_object(Bucket=args.bucket, Key=CURRENT_KEY)["Body"].read())
    print(f"  current reference version {current.get('version')} ({len(current.get('entries', []))} entries)")

    if args.dry_run:
        print("DRY RUN: not embedding or publishing. Sample normalized entries:")
        for e in entries[:5]:
            print("   ", {k: e[k] for k in ("name", "severity", "classification", "exclusion_type", "uei")})
        return

    bedrock = boto3.client("bedrock-runtime", region_name="us-east-2")
    doc = build_reference_doc(current, entries, _titan_embed(bedrock))
    n = publish(s3, args.bucket, doc)
    print(f"PUBLISHED reference version {n}: {len(doc['entries'])} entries "
          f"({len(entries)} real SAM + {len(doc['entries']) - len(entries)} synthetic restricted). "
          f"Component B picks it up within REFERENCE_TTL_SECONDS.")


if __name__ == "__main__":
    main()
