"""Component G - Scheduled Reference Refresher (v3.4.0, DEC-24).

Keeps the Do Not Pay reference list current automatically. On a daily EventBridge
Scheduler schedule it re-pulls the real SAM.gov exclusions (keyless OpenSanctions
mirror, same source as the v4 publish, DEC-22), re-embeds them (Titan, DEC-19), and
publishes a NEW versioned reference document through the existing versioned-store
lifecycle (DEC-18) - but ONLY when the SAM list actually changed, so an unchanged day
does not churn the version or spend embedding cost.

The other sources - the real OIG LEIE (DEC-30) and the synthetic SSA DMF and TOP - are
carried verbatim with their existing embeddings; only the real SAM entries are refreshed. Matching logic
mirrors scripts/ingest_sam_exclusions.py (shared, test-pinned, like the DEC-16
duplicated idempotency claim).
"""
from __future__ import annotations

import csv
import datetime
import io
import json
import os
import urllib.request

import boto3
from botocore.exceptions import ClientError

_s3 = None
_bedrock = None

OPENSANCTIONS_INDEX = "https://data.opensanctions.org/datasets/latest/us_sam_exclusions/index.json"
EMBED_MODEL = os.environ.get("EMBED_MODEL", "amazon.titan-embed-text-v2:0")
CURRENT_KEY = "reference/current.json"
SAM_SOURCE = "sam_exclusions"
_SCHEMA_TO_CLASS = {"Person": "Individual", "LegalEntity": "Entity",
                    "Company": "Entity", "Organization": "Entity"}


def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _bedrock_client():
    global _bedrock
    if _bedrock is None:
        _bedrock = boto3.client("bedrock-runtime")
    return _bedrock


def _embed(text: str) -> list[float]:
    r = _bedrock_client().invoke_model(
        modelId=EMBED_MODEL,
        body=json.dumps({"inputText": str(text or ""), "normalize": True}),
        accept="application/json", contentType="application/json")
    return json.loads(r["body"].read())["embedding"]


def _fetch_sam(limit: int) -> list[dict]:
    """Resolve the current targets.simple.csv from the latest OpenSanctions dataset
    index and download it (keyless, no rate limit). Returns raw CSV rows, capped."""
    req = urllib.request.Request(OPENSANCTIONS_INDEX, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (fixed https host)
        index = json.loads(resp.read())
    csv_url = next((r["url"] for r in index.get("resources", [])
                    if r.get("name") == "targets.simple.csv"), None)
    if not csv_url:
        raise RuntimeError("targets.simple.csv not found in the OpenSanctions index")
    req = urllib.request.Request(csv_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310 (fixed https host)
        reader = csv.DictReader(io.StringIO(resp.read().decode("utf-8")))
        rows = []
        for r in reader:  # keep only the cap in memory, not the whole ~100k-row file
            rows.append(r)
            if limit and len(rows) >= limit:
                break
    return rows


def _normalize_row(row: dict) -> dict | None:
    """One OpenSanctions CSV row -> reference schema, or None to drop. Keep only Active
    rows; match the STATUS token exactly ('Inactive' contains the substring 'active')."""
    sanctions = str(row.get("sanctions") or "")

    def _status(s):
        parts = [p.strip() for p in s.split(" - ")]
        return parts[1].lower() if len(parts) >= 2 else ""
    if not any(_status(s) == "active" for s in sanctions.split(";")):
        return None
    name = str(row.get("name") or "").strip()
    if not name:
        return None
    program = sanctions.split(" - ")[0].strip() if sanctions else ""
    uei = str(row.get("identifiers") or "").split(";")[0].strip()
    return {
        "name": name, "tin": "", "uei": uei or None, "source": SAM_SOURCE,
        "severity": "high",
        "classification": _SCHEMA_TO_CLASS.get(str(row.get("schema") or "").strip(), "Entity"),
        "exclusion_type": program or None, "excluding_agency": None,
    }


def _normalize_all(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for row in rows:
        e = _normalize_row(row)
        if e is None:
            continue
        k = (e["name"].lower(), e["uei"])
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def _sam_keys(entries: list[dict]) -> set:
    return {(e["name"].lower(), e.get("uei")) for e in entries if e.get("source") == SAM_SOURCE}


def _build_doc(current: dict, real_entries: list[dict]) -> dict:
    kept = [e for e in current.get("entries", []) if e.get("source") != SAM_SOURCE]
    embedded = [{**e, "embedding": _embed(e["name"]), "embedding_model": EMBED_MODEL}
                for e in real_entries]
    sources = dict(current.get("sources", {}))
    sources[SAM_SOURCE] = ("SAM.gov exclusions (GSA System for Award Management) - REAL federal "
                           "debarment/suspension list, auto-refreshed daily (Component G, DEC-24)")
    return {
        "version": current.get("version", 0) + 1,
        "updated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "updated_by": f"component_g_refresher (SAM auto-refresh; {len(embedded)} real SAM, {len(kept)} carried verbatim)",
        "sources": sources,
        "semantic_threshold": current.get("semantic_threshold", 0.72),
        "entries": kept + embedded,
    }


def _publish(bucket: str, doc: dict) -> int:
    n = doc["version"]
    body = json.dumps(doc, indent=2).encode()
    try:
        _s3_client().put_object(Bucket=bucket, Key=f"reference/versions/{n}.json",
                                Body=body, ContentType="application/json", IfNoneMatch="*")
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("PreconditionFailed", "412"):
            raise RuntimeError(f"version {n} already exists (concurrent publish); skipping") from exc
        raise
    _s3_client().put_object(Bucket=bucket, Key=CURRENT_KEY, Body=body, ContentType="application/json")
    return n


def handler(event, context=None):
    bucket = os.environ["REFERENCE_BUCKET"]
    limit = int(os.environ.get("REFRESH_LIMIT", "90"))
    current = json.loads(_s3_client().get_object(Bucket=bucket, Key=CURRENT_KEY)["Body"].read())

    try:
        real = _normalize_all(_fetch_sam(limit))
    except Exception as exc:  # never crash the schedule on an upstream hiccup
        print(f"refresher: SAM fetch failed, keeping current version {current.get('version')}: "
              f"{type(exc).__name__}: {exc}")
        return {"refreshed": False, "reason": "fetch_error", "version": current.get("version")}

    if not real:
        print("refresher: SAM feed returned no active entries; keeping current version")
        return {"refreshed": False, "reason": "empty_feed", "version": current.get("version")}

    if _sam_keys(real) == _sam_keys(current.get("entries", [])):
        print(f"refresher: SAM list unchanged ({len(real)} entries); keeping version {current.get('version')}")
        return {"refreshed": False, "reason": "unchanged", "version": current.get("version")}

    n = _publish(bucket, _build_doc(current, real))
    print(f"refresher: published reference version {n} ({len(real)} real SAM entries)")
    return {"refreshed": True, "version": n, "sam_entries": len(real)}
