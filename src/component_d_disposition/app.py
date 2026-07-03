"""Component D - Disposition Router & Audit Logger.

SQS-triggered worker (shared queue_worker_stage module). For each scored payment:
1. Write an immutable AUDIT RECORD to the S3 Object Lock bucket (commitment 4).
   The record is a compliance artifact: decision + evidence + provenance + a
   SHA-256 integrity hash (Object Lock stops deletion/overwrite; the hash proves
   the content itself wasn't tampered - defense in depth).
2. If disposition == "review", route to the human-review queue (commitment 2)
   and post a webhook notification (DEC-7) whose URL is read from Secrets Manager.

Ordering: the audit write happens FIRST and is authoritative. Routing follows.
This avoids duplicate review items if a retry occurs (a re-driven message may
write a second audit version - acceptable, both are truthful - but never
double-routes before the audit exists).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import uuid
from urllib import request as urlrequest

import boto3

_s3 = None
_sqs = None
_secrets = None
_webhook_url = None

COMPONENT_VERSION = "0.4.0"


def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _sqs_client():
    global _sqs
    if _sqs is None:
        _sqs = boto3.client("sqs")
    return _sqs


def _secrets_client():
    global _secrets
    if _secrets is None:
        _secrets = boto3.client("secretsmanager")
    return _secrets


def _webhook_endpoint() -> str:
    global _webhook_url
    if _webhook_url is None:
        # DEC-7: least-privilege GetSecretValue on exactly this one ARN.
        arn = os.environ["WEBHOOK_SECRET_ARN"]
        _webhook_url = _secrets_client().get_secret_value(SecretId=arn)["SecretString"]
    return _webhook_url


def audit_record(payment: dict) -> dict:
    risk = payment.get("risk", {})
    disposition = risk.get("disposition")
    record = {
        "schema_version": "1.0",
        "audit_id": str(uuid.uuid4()),
        "payment_id": payment.get("payment_id"),
        "audited_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "decision": {
            "disposition": disposition,
            "risk_score": risk.get("score"),
            "reasons": risk.get("reasons", []),
        },
        "evidence": {
            "matches": payment.get("enrichment", {}).get("matches", []),
            "match_count": payment.get("enrichment", {}).get("match_count", 0),
            "highest_confidence": payment.get("enrichment", {}).get("highest_confidence", 0),
        },
        "payment": {k: payment[k] for k in ("payee", "amount", "payee_tin") if k in payment},
        "provenance": {
            "pipeline": ["intake", "enrichment", "risk_scoring", "disposition"],
            "component_versions": {"disposition": COMPONENT_VERSION},
        },
        "routing": {"routed_to_review": disposition == "review"},
    }
    digest = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    record["integrity"] = {
        "algorithm": "sha256",
        "sha256": digest,
        "canonical": "all fields except integrity, sorted-key compact JSON",
    }
    return record


def _audit_key(record: dict) -> str:
    date_path = record["audited_at"][:10].replace("-", "/")  # yyyy/mm/dd
    return f"audit/{date_path}/{record['payment_id']}-{record['audit_id']}.json"


def _route_to_review(payment: dict, record: dict) -> None:
    _sqs_client().send_message(
        QueueUrl=os.environ["REVIEW_QUEUE_URL"],
        MessageBody=json.dumps({
            "payment_id": payment.get("payment_id"),
            "audit_id": record["audit_id"],
            "risk": payment.get("risk"),
        }),
    )
    body = json.dumps({
        "text": f"Payment {payment.get('payment_id')} routed to human review "
                f"(score {payment.get('risk', {}).get('score')})",
        "payment_id": payment.get("payment_id"),
        "audit_id": record["audit_id"],
    }).encode()
    req = urlrequest.Request(
        _webhook_endpoint(), data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    urlrequest.urlopen(req, timeout=5)  # noqa: S310 - URL is an operator-provided secret, not user input


def handler(event, context=None):
    bucket = os.environ["AUDIT_BUCKET_NAME"]
    failures = []
    for record in event.get("Records", []):
        try:
            payment = json.loads(record["body"])
            audit = audit_record(payment)
            # Authoritative write first; inherits the bucket's Object Lock
            # COMPLIANCE default retention (no per-request headers).
            _s3_client().put_object(
                Bucket=bucket,
                Key=_audit_key(audit),
                Body=json.dumps(audit).encode(),
                ContentType="application/json",
            )
            if audit["routing"]["routed_to_review"]:
                _route_to_review(payment, audit)
        except Exception:
            failures.append({"itemIdentifier": record.get("messageId")})
    return {"batchItemFailures": failures}
