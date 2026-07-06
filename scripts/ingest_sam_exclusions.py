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
import datetime
import json
import os
import sys
import time
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
SEVERITY_BY_EXCLUSION_TYPE = {
    "Prohibition/Restriction": "high",
    "Ineligible (Proceedings Completed)": "high",
    "Ineligible (Proceedings Pending)": "medium",
    "Voluntary Exclusion": "medium",
}


# ---- fetch (real GSA API) ---------------------------------------------------

def fetch_exclusions(api_key: str, endpoint: str, limit: int) -> list[dict]:
    """Paginated pull of ACTIVE exclusions (size<=10 per the v4 contract). Capped at
    `limit` so the embedded reference doc stays within the in-store-cosine budget.
    Returns raw records; normalization is a separate, testable step."""
    out: list[dict] = []
    page = 0
    while len(out) < limit and page <= 999:
        qs = urllib.parse.urlencode({"api_key": api_key, "page": page, "size": 10})
        req = urllib.request.Request(f"{endpoint}?{qs}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed https host)
            payload = json.loads(resp.read())
        records = _records_from_payload(payload)
        if not records:
            break
        out.extend(records)
        page += 1
        time.sleep(0.2)  # be polite to the rate-limited API
    return out[:limit]


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

def _record_name(raw: dict) -> str:
    """SAM stores firms under entityName and individuals under name parts. Prefer an
    explicit entity/legal-business name; fall back to assembled person-name parts."""
    for k in ("entityName", "exclusionName", "name", "legalBusinessName"):
        v = raw.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    parts = [raw.get("firstName"), raw.get("middleName"), raw.get("lastName")]
    assembled = " ".join(p.strip() for p in parts if isinstance(p, str) and p.strip())
    return assembled.strip()


def _is_active(raw: dict) -> bool:
    status = str(raw.get("recordStatus") or raw.get("classificationStatus") or "").strip().lower()
    if status:
        return status == "active"
    # some payloads use a boolean/date instead of a status string
    if "isActive" in raw:
        return bool(raw["isActive"])
    term = raw.get("terminationDate") or raw.get("terminationDateData")
    return not term  # no termination date -> treat as active


def normalize_record(raw: dict) -> dict | None:
    """Map one raw SAM exclusion to the reference-list schema, or None to drop it.
    SAM has NO TIN, so tin is empty and matching runs on name only (exact/fuzzy/
    semantic); ueiSAM is carried for audit provenance, not for matching."""
    if not _is_active(raw):
        return None
    name = _record_name(raw)
    if not name:
        return None
    exclusion_type = str(raw.get("exclusionType") or "").strip()
    classification = str(raw.get("classificationType") or raw.get("classification") or "").strip()
    return {
        "name": name,
        "tin": "",  # SAM keys on name / UEI, never a TIN
        "uei": (raw.get("ueiSAM") or raw.get("uei") or "").strip() or None,
        "source": SAM_SOURCE,
        "severity": SEVERITY_BY_EXCLUSION_TYPE.get(exclusion_type, "high"),
        "classification": classification or None,
        "exclusion_type": exclusion_type or None,
        "excluding_agency": (raw.get("excludingAgencyName") or "").strip() or None,
    }


def normalize_all(raw_records: list[dict]) -> list[dict]:
    """Normalize, drop inactive/nameless, and dedupe on (normalized name, uei)."""
    seen: set = set()
    entries: list[dict] = []
    for raw in raw_records:
        e = normalize_record(raw)
        if e is None:
            continue
        k = (e["name"].lower(), e["uei"])
        if k in seen:
            continue
        seen.add(k)
        entries.append(e)
    return entries


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
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--limit", type=int, default=300, help="cap on real SAM entries (in-store-cosine budget)")
    ap.add_argument("--dry-run", action="store_true", help="fetch + normalize + summarize, do NOT publish")
    args = ap.parse_args()

    api_key = os.environ.get("SAM_API_KEY")
    if not api_key:
        sys.exit("SAM_API_KEY is not set. Provision a SAM.gov system-account API key "
                 "(https://open.gsa.gov/api/exclusions-api/) and export it; it is never committed.")

    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")
    s3 = boto3.client("s3", region_name="us-east-2")

    print(f"Fetching up to {args.limit} active SAM exclusions from {args.endpoint} ...")
    raw = fetch_exclusions(api_key, args.endpoint, args.limit)
    entries = normalize_all(raw)
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
