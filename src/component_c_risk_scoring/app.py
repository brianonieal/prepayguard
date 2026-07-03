"""Component C - Risk-Scoring & Decision Engine.

SQS-triggered worker (shared queue_worker_stage module). Reads the `enrichment`
block Component B attached, computes a transparent rule-based risk score, and
emits a three-way disposition (DEC-14), then forwards to the output queue
(consumed by Component D, which writes the audit record and routes review items).

Disposition rules (DEC-14):
- TIN match (strong identity)          -> reject
- name match (potential, false-pos)    -> review  (routes to a human)
- no reference-source match            -> approve
Scores >= 80 reject, >= 30 review, else approve. Name matches are capped below
the reject threshold so an identity-uncertain hit always gets human eyes.
"""
from __future__ import annotations

import json
import os

import boto3

_sqs = None

SEVERITY_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.3}
REJECT_THRESHOLD = 80
REVIEW_THRESHOLD = 30
NAME_MATCH_CAP = 60  # keeps identity-uncertain (name-only) matches in "review"


def _sqs_client():
    global _sqs
    if _sqs is None:
        _sqs = boto3.client("sqs")
    return _sqs


def score(payment: dict) -> dict:
    matches = payment.get("enrichment", {}).get("matches", [])
    reasons: list[str] = []
    best = 0.0

    for m in matches:
        confidence = m.get("confidence", 0)
        weight = SEVERITY_WEIGHT.get(m.get("severity", "high"), 1.0)
        if m.get("matched_on") == "tin":
            value = confidence * weight
        else:
            # Name/fuzzy hits are POTENTIAL matches (false-positive risk): cap
            # them below the reject line so they route to human review.
            value = min(confidence * weight, NAME_MATCH_CAP)
        best = max(best, value)
        reasons.append(
            f"{m.get('matched_on')} match on {m.get('source')} (severity {m.get('severity')})"
        )

    if best >= REJECT_THRESHOLD:
        disposition = "reject"
    elif best >= REVIEW_THRESHOLD:
        disposition = "review"
    else:
        disposition = "approve"
        if not reasons:
            reasons.append("no reference-source matches")

    payment["risk"] = {"score": round(best), "disposition": disposition, "reasons": reasons}
    return payment


def handler(event, context=None):
    out_url = os.environ["OUTPUT_QUEUE_URL"]
    failures = []
    for record in event.get("Records", []):
        try:
            payment = json.loads(record["body"])
            scored = score(payment)
            _sqs_client().send_message(QueueUrl=out_url, MessageBody=json.dumps(scored))
        except Exception:
            failures.append({"itemIdentifier": record.get("messageId")})
    return {"batchItemFailures": failures}
