"""Component B - Enrichment & Reference-Match Service.

SQS-triggered worker (shared queue_worker_stage module). For each payment it
matches the payee against a bundled synthetic reference list modeling the real
Treasury Do Not Pay sources (DEC-14), attaches an `enrichment` block, and
forwards the enriched payment to the output queue (consumed by Component C).

Matching (DEC-14):
- TIN exact (normalized)         -> confidence 95
- name exact (normalized)        -> confidence 80
- name fuzzy (difflib >= 0.90)   -> confidence 60
A hit is a POTENTIAL match; the pay/review/reject decision is Component C's.
"""
from __future__ import annotations

import difflib
import json
import os
import re
from pathlib import Path
from typing import Any

import boto3

_sqs = None
_reference: dict | None = None

FUZZY_THRESHOLD = 0.90


def _sqs_client():
    global _sqs
    if _sqs is None:
        _sqs = boto3.client("sqs")
    return _sqs


def _reference_data() -> dict:
    global _reference
    if _reference is None:
        with open(Path(__file__).resolve().parent / "reference_data.json", encoding="utf-8") as fh:
            _reference = json.load(fh)
    return _reference


def _normalize_name(name: Any) -> str:
    n = re.sub(r"[^a-z0-9\s]", " ", str(name or "").lower())
    return re.sub(r"\s+", " ", n).strip()


def _normalize_tin(tin: Any) -> str:
    return re.sub(r"\D", "", str(tin or ""))


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

    return matches


def enrich(payment: dict) -> dict:
    matches = match_against_reference(payment)
    payment["enrichment"] = {
        "matches": matches,
        "match_count": len(matches),
        "highest_confidence": max((m["confidence"] for m in matches), default=0),
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
