"""Component B - Enrichment & Reference-Match Service.

SQS-triggered worker (shared queue_worker_stage module). For each payment it
matches the payee against the Do Not Pay reference list (DEC-14), attaches an
`enrichment` block, and forwards the enriched payment to the output queue
(consumed by Component C).

Reference data (v2.1.0): the list lives in the versioned reference store
(s3://REFERENCE_BUCKET/reference/current.json), fetched with a short warm-cache
TTL so admin publishes take effect within a minute. The version screened
against rides the enrichment block into the audit record (the citation).
Failure posture: an S3 error with a warm cache serves the cached copy; with NO
cache it raises, so the message takes the retry/DLQ path (commitment 2) rather
than screening against unknown data. The bundled reference_data.json remains
only as the version-1 seed source and the no-store test/local fallback.

Matching (DEC-14):
- TIN exact (normalized)         -> confidence 95
- name exact (normalized)        -> confidence 80
- name fuzzy (difflib >= 0.90)   -> confidence 60
- name SEMANTIC (v2.2.0)         -> Bedrock-embedding cosine >= threshold, run only
                                    when the string methods above found nothing.
A hit is a POTENTIAL match; the pay/review/reject decision is Component C's. A
semantic hit is capped to REVIEW by C (never a definitive match), like a fuzzy one.
"""
from __future__ import annotations

import difflib
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any

import boto3

_sqs = None
_s3 = None
_bedrock = None
_reference: dict | None = None
_reference_fetched = 0.0

FUZZY_THRESHOLD = 0.90
REFERENCE_KEY = "reference/current.json"


def _sqs_client():
    global _sqs
    if _sqs is None:
        _sqs = boto3.client("sqs")
    return _sqs


def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _reference_data() -> dict:
    global _reference, _reference_fetched
    ttl = int(os.environ.get("REFERENCE_TTL_SECONDS", "60"))
    if _reference is not None and time.time() - _reference_fetched < ttl:
        return _reference

    bucket = os.environ.get("REFERENCE_BUCKET")
    if bucket:
        try:
            body = _s3_client().get_object(Bucket=bucket, Key=REFERENCE_KEY)["Body"].read()
            _reference = json.loads(body)
            _reference_fetched = time.time()
        except Exception:
            if _reference is None:
                raise  # no known list at all -> retry/DLQ, never screen blind
            # stale-but-known beats unknown; the next TTL expiry retries the fetch
        return _reference

    # No store configured (tests/local): the bundled seed copy.
    if _reference is None:
        with open(Path(__file__).resolve().parent / "reference_data.json", encoding="utf-8") as fh:
            _reference = json.load(fh)
        _reference_fetched = time.time()
    return _reference


def _normalize_name(name: Any) -> str:
    n = re.sub(r"[^a-z0-9\s]", " ", str(name or "").lower())
    return re.sub(r"\s+", " ", n).strip()


def _normalize_tin(tin: Any) -> str:
    return re.sub(r"\D", "", str(tin or ""))


def _bedrock_client():
    global _bedrock
    if _bedrock is None:
        _bedrock = boto3.client("bedrock-runtime")
    return _bedrock


def _embed(text: str) -> list[float]:
    resp = _bedrock_client().invoke_model(
        modelId=os.environ.get("EMBED_MODEL", "amazon.titan-embed-text-v2:0"),
        body=json.dumps({"inputText": str(text or ""), "normalize": True}),
        accept="application/json", contentType="application/json",
    )
    return json.loads(resp["body"].read())["embedding"]


def _cosine(u, v) -> float:
    if not u or not v or len(u) != len(v):
        return 0.0
    dot = sum(a * b for a, b in zip(u, v, strict=True))  # lengths guarded equal above
    nu = math.sqrt(sum(a * a for a in u)) or 1.0
    nv = math.sqrt(sum(b * b for b in v)) or 1.0
    return dot / (nu * nv)


def _semantic_threshold() -> float:
    try:
        return float(_reference_data().get("semantic_threshold"))  # versioned with the list
    except (TypeError, ValueError):
        return float(os.environ.get("SEMANTIC_THRESHOLD", "0.72"))


def _semantic_match(payment: dict) -> list[dict]:
    """v2.2.0: catch payee variants exact/fuzzy string matching missed, via Bedrock
    embeddings cosine'd against the versioned per-entry vectors (no vector DB).
    Runs ONLY when the string methods found nothing, bounding Bedrock calls to the
    ambiguous cases. On a Bedrock error, degrade to rule-based screening (the
    deterministic rules already ran) rather than DLQ the payment."""
    entries = [e for e in _reference_data()["entries"] if e.get("embedding")]
    if not entries or not str(payment.get("payee") or "").strip():
        return []
    try:
        vec = _embed(payment.get("payee"))
    except Exception:
        return []
    threshold = _semantic_threshold()
    best = None
    for entry in entries:
        sim = _cosine(vec, entry["embedding"])
        if sim >= threshold and (best is None or sim > best[1]):
            best = (entry, sim)
    if best is None:
        return []
    entry, sim = best
    return [{"source": entry["source"], "severity": entry["severity"],
             "matched_on": "name_semantic", "confidence": round(sim * 100),
             "similarity": round(sim, 4)}]


def match_against_reference(payment: dict) -> list[dict]:
    matches: list[dict] = []
    payee = _normalize_name(payment.get("payee"))
    tin = _normalize_tin(payment.get("payee_tin"))

    for entry in _reference_data()["entries"]:
        entry_name = _normalize_name(entry["name"])
        entry_tin = _normalize_tin(entry["tin"])
        base = {"source": entry["source"], "severity": entry["severity"]}

        if tin and entry_tin and tin == entry_tin:
            matches.append({**base, "matched_on": "tin", "confidence": 95})
        elif payee and entry_name and payee == entry_name:
            matches.append({**base, "matched_on": "name_exact", "confidence": 80})
        elif payee and entry_name and difflib.SequenceMatcher(None, payee, entry_name).ratio() >= FUZZY_THRESHOLD:
            matches.append({**base, "matched_on": "name_fuzzy", "confidence": 60})

    # Semantic net: only for payees the deterministic string rules cleared.
    if not matches:
        matches.extend(_semantic_match(payment))
    return matches


def enrich(payment: dict) -> dict:
    matches = match_against_reference(payment)
    payment["enrichment"] = {
        "matches": matches,
        "match_count": len(matches),
        "highest_confidence": max((m["confidence"] for m in matches), default=0),
        # v2.1.0: cite the exact list version screened against (0 = bundled seed).
        "reference_version": _reference_data().get("version", 0),
    }
    return payment


def handler(event, context=None):
    out_url = os.environ["OUTPUT_QUEUE_URL"]
    failures = []
    for record in event.get("Records", []):
        try:
            payment = json.loads(record["body"])
            enriched = enrich(payment)
            _sqs_client().send_message(QueueUrl=out_url, MessageBody=json.dumps(enriched))
        except Exception:
            # Partial-batch failure: this one message is retried / DLQ'd; the rest
            # of the batch is not re-driven (queue_worker_stage sets
            # ReportBatchItemFailures).
            failures.append({"itemIdentifier": record.get("messageId")})
    return {"batchItemFailures": failures}
