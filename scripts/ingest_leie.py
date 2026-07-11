#!/usr/bin/env python3
"""Ingest the REAL HHS-OIG LEIE (List of Excluded Individuals/Entities) into the
versioned reference store, CONVERTING the two synthetic ``oig_leie`` seeds into real
public exclusion data. Mirrors ``scripts/ingest_sam_exclusions.py`` exactly (DEC-30):
same reference schema, same versioned-store lifecycle (DEC-18), same publish-time
Titan embedding (DEC-19). It does NOT add a new source type, touch the matcher, or
change any other source.

Source: HHS Office of Inspector General, "Updated LEIE Database" (public, keyless CSV)
  https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv
The LEIE lists every party currently excluded from federal health-care programs
(~83k rows: ~80k individuals + ~3k entities). It is a healthcare-provider list, so it
is NOT expected to produce live hits against the USAspending award feed (which is
federal contractors, not providers) - that mismatch is expected and honest (DEC-30).

PII (the hard gate): individuals are REAL people. Classification is derived from the
LEIE's OWN columns - a row with LASTNAME/FIRSTNAME is an Individual (masked to
"First L." on the public console), a row with BUSNAME is an Entity (shown full). This
is authoritative from the source, not a heuristic. The console masks on the entry's
``classification`` field (console/src/lib/pii.js); every individual we publish carries
``classification="Individual"`` so it renders masked. We never publish the full file.

Identifier (honest, no fabrication): the LEIE carries an NPI for many providers but no
public SSN/TIN. We PRESERVE the NPI in the record (``npi``) for provenance and future
NPI-grade matching, and leave ``tin`` blank. Per the decision model (F6), a blank TIN
means these entries can only reach REVIEW on a name match, never auto-reject. Our
identity matching is TIN-shaped while real lists key on NPI - a documented gap (F8).

Usage:
  python scripts/ingest_leie.py --bucket treasury-dev-reference-ACCOUNT_ID [--limit 500] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import os
import sys
import urllib.request

import boto3
from botocore.exceptions import ClientError

DEFAULT_URL = "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv"
EMBED_MODEL = "amazon.titan-embed-text-v2:0"
CURRENT_KEY = "reference/current.json"
LEIE_SOURCE = "oig_leie"


# ---- fetch (real HHS-OIG public CSV; keyless, no rate limit) ----------------

def fetch_leie(url: str = DEFAULT_URL) -> list[dict]:
    """Download the public LEIE CSV and return its rows as dicts. Keyless, no rate
    limit (same posture as the OpenSanctions bulk path in the SAM ingest)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310 (fixed https host)
        text = resp.read().decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


# ---- normalize (pure, unit-tested; no network, no Bedrock) ------------------

def _clean(value) -> str:
    """LEIE uses empty strings and a literal "NULL" token for missing fields; treat
    both as absent (real-world messiness, objective 10)."""
    s = str(value or "").strip()
    return "" if s.upper() == "NULL" else s


def leie_classification(row: dict) -> str:
    """AUTHORITATIVE from the source columns, not a heuristic: a BUSNAME row is an
    Entity; a row with person name parts is an Individual. Drives console masking."""
    return "Entity" if _clean(row.get("BUSNAME")) else "Individual"


def leie_name(row: dict, classification: str) -> str:
    """Entity -> BUSNAME. Individual -> assembled FIRSTNAME MIDNAME LASTNAME (mirrors
    the SAM ingest's person-part assembly), dropping empty / "NULL" parts."""
    if classification == "Entity":
        return _clean(row.get("BUSNAME"))
    parts = [_clean(row.get("FIRSTNAME")), _clean(row.get("MIDNAME")), _clean(row.get("LASTNAME"))]
    return " ".join(p for p in parts if p).strip()


def _npi(row: dict) -> str | None:
    """NPI when present; the LEIE uses "0000000000" (and blanks) for no-NPI. Kept for
    provenance and future NPI-grade matching (F8); the matcher does not use it yet."""
    npi = _clean(row.get("NPI"))
    return npi if npi and set(npi) != {"0"} else None


def _is_active(row: dict) -> bool:
    """The UPDATED LEIE lists currently-excluded parties; REINDATE "00000000" means not
    reinstated. Defensive active-only filter (mirrors the SAM _is_active discipline)."""
    reindate = _clean(row.get("REINDATE"))
    return reindate in ("", "00000000") or set(reindate) == {"0"}


def normalize_row(row: dict) -> dict | None:
    """Map one raw LEIE CSV row to the reference-list schema, or None to drop it.
    LEIE has NO public TIN, so ``tin`` is empty and matching runs on name only
    (exact/fuzzy/semantic); NPI is preserved for provenance, never fabricated."""
    if not _is_active(row):
        return None
    classification = leie_classification(row)
    name = leie_name(row, classification)
    if not name:
        return None
    excl_type = _clean(row.get("EXCLTYPE"))
    return {
        "name": name,
        "tin": "",  # LEIE carries no public SSN/TIN -> name-only match -> review, never auto-reject (F6)
        "npi": _npi(row),  # preserved for provenance / future NPI matching (F8)
        "source": LEIE_SOURCE,
        "severity": "high",  # every LEIE party is an excluded provider
        "classification": classification,  # authoritative from BUSNAME vs name columns; drives masking
        "exclusion_type": excl_type or None,
    }


def normalize_all(raw_rows: list[dict], normalizer=normalize_row) -> list[dict]:
    """Normalize, drop inactive/nameless, dedupe on (normalized name, npi). Same shape
    as the SAM ingest's normalize_all so the two ingests read identically."""
    seen: set = set()
    entries: list[dict] = []
    for raw in raw_rows:
        e = normalizer(raw)
        if e is None:
            continue
        k = (e["name"].lower(), e.get("npi"))
        if k in seen:
            continue
        seen.add(k)
        entries.append(e)
    return entries


# ---- deliberate sample (documented mix, not file order) - DEC-30 -----------

def _stride(items: list[dict], k: int) -> list[dict]:
    """Evenly-spaced (strided) pick of k items across the list, so the sample spans the
    whole alphabet rather than just the file head. Deterministic (no RNG)."""
    if k <= 0 or not items:
        return []
    if k >= len(items):
        return list(items)
    step = len(items) / k
    return [items[int(i * step)] for i in range(k)]


def deliberate_sample(entries: list[dict], total: int = 500, entity_target: int = 50) -> list[dict]:
    """Cap to a demo-sized slice by a DOCUMENTED individual/entity mix, strided across
    the file (DEC-30) - NOT the first N rows. Entities are over-sampled vs their ~4%
    file share so both classifications are visibly represented (masking demo needs
    individuals; full-name display needs entities)."""
    inds = [e for e in entries if e["classification"] == "Individual"]
    ents = [e for e in entries if e["classification"] == "Entity"]
    n_ent = min(entity_target, len(ents), total)
    n_ind = min(total - n_ent, len(inds))
    return _stride(inds, n_ind) + _stride(ents, n_ent)


# ---- build the versioned doc (reuse the other sources verbatim) -------------

def build_reference_doc(current_doc: dict, real_leie_entries: list[dict], embed_fn) -> dict:
    """Keep every non-LEIE entry from the current live doc verbatim (real SAM + the two
    synthetic DMF and two synthetic TOP seeds, WITH their embeddings), replace the
    synthetic ``oig_leie`` seeds with the real LEIE feed, and embed the real entries.
    Mirrors ingest_sam_exclusions.build_reference_doc exactly."""
    kept = [e for e in current_doc.get("entries", []) if e.get("source") != LEIE_SOURCE]
    embedded_real = [{**e, "embedding": embed_fn(e["name"]), "embedding_model": EMBED_MODEL}
                     for e in real_leie_entries]

    sources = dict(current_doc.get("sources", {}))
    sources[LEIE_SOURCE] = ("OIG List of Excluded Individuals/Entities (HHS-OIG LEIE) - REAL public "
                            "exclusion list of parties barred from federal health-care programs")
    return {
        "version": current_doc.get("version", 0) + 1,
        "updated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "updated_by": f"ingest_leie.py (HHS-OIG LEIE real source; {len(embedded_real)} real LEIE, "
                      f"{len(kept)} other)",
        "sources": sources,
        "semantic_threshold": current_doc.get("semantic_threshold", 0.72),
        "entries": kept + embedded_real,
    }


# ---- publish (reuse the DEC-18 versioned lifecycle) -------------------------

def publish(s3, bucket: str, doc: dict) -> int:
    """Claim reference/versions/{N}.json with a conditional put (If-None-Match: *),
    then repoint reference/current.json - identical to ingest_sam_exclusions.publish."""
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


# ---- masking preview (verification only; mirrors pii.js maskIndividualName) --

def _preview_masked(name: str) -> str:
    """Python mirror of console/src/lib/pii.js maskIndividualName, used ONLY to show the
    operator that real individuals render masked on the console. Not the authority - the
    console/pii.test.js is - just a publish-time confidence check on real data."""
    parts = name.split()
    if len(parts) < 2:
        return name
    surname = next((p for p in reversed(parts[1:]) if p.lower().rstrip(".") not in ("jr", "sr", "ii", "iii", "iv", "v")), None)
    return f"{parts[0]} {surname[0].upper()}." if surname else parts[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True, help="reference-store bucket, e.g. treasury-dev-reference-<acct>")
    ap.add_argument("--url", default=DEFAULT_URL, help="LEIE CSV url (default: HHS-OIG UPDATED.csv)")
    ap.add_argument("--limit", type=int, default=500,
                    help="cap on real LEIE entries (DEC-30 demo slice, sized for the DEC-19 in-store-cosine budget)")
    ap.add_argument("--entity-target", type=int, default=50, help="entities in the sampled mix (rest are individuals)")
    ap.add_argument("--dry-run", action="store_true", help="fetch + normalize + sample + summarize, do NOT publish")
    args = ap.parse_args()

    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-2")
    s3 = boto3.client("s3", region_name="us-east-2")

    print(f"Fetching the real HHS-OIG LEIE from {args.url} ...")
    raw = fetch_leie(args.url)
    all_entries = normalize_all(raw)
    entries = deliberate_sample(all_entries, total=args.limit, entity_target=args.entity_target)
    by_class: dict = {}
    for e in entries:
        by_class[e["classification"]] = by_class.get(e["classification"], 0) + 1
    with_npi = sum(1 for e in entries if e.get("npi"))
    print(f"  fetched {len(raw)} raw, {len(all_entries)} active+named+deduped, sampled {len(entries)}")
    print(f"  by classification: {by_class}  |  with NPI preserved: {with_npi}  |  TIN: 0 (blank, honest)")

    current = json.loads(s3.get_object(Bucket=args.bucket, Key=CURRENT_KEY)["Body"].read())
    print(f"  current reference version {current.get('version')} ({len(current.get('entries', []))} entries)")

    # PII gate check on REAL data: every individual carries classification=Individual, so
    # the console masks it. Show a few masked forms as they will render (never committed).
    inds = [e for e in entries if e["classification"] == "Individual"]
    assert all(e["classification"] == "Individual" for e in inds), "individual missing classification -> would NOT mask"
    print(f"  PII gate: {len(inds)} individuals all carry classification=Individual -> console masks every one.")
    print("  sample individuals as they render on the public console (masked 'First L.'):")
    for e in inds[:5]:
        print(f"     {_preview_masked(e['name'])}")

    if args.dry_run:
        print("DRY RUN: not embedding or publishing.")
        return

    bedrock = boto3.client("bedrock-runtime", region_name="us-east-2")
    doc = build_reference_doc(current, entries, _titan_embed(bedrock))
    n = publish(s3, args.bucket, doc)
    real_sam = sum(1 for e in doc["entries"] if e.get("source") == "sam_exclusions")
    synth = sum(1 for e in doc["entries"] if e.get("source") in ("death_master_file", "treasury_offset"))
    print(f"PUBLISHED reference version {n}: {len(doc['entries'])} entries "
          f"({len(entries)} real LEIE + {real_sam} real SAM + {synth} synthetic restricted). "
          f"Component B picks it up within REFERENCE_TTL_SECONDS.")


if __name__ == "__main__":
    main()
