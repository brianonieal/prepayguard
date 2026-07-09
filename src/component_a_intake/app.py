"""Component A - Payment Intake API handler.

Idempotency via payment-ID deduplication (graded commitment 1, DEC-13):
a DynamoDB conditional write with an explicit PENDING -> SENT state machine and
original-result replay. A duplicate payment_id returns the ORIGINAL outcome
(true idempotent replay), never a rejection.

Ordering: write PENDING -> SendMessage -> update SENT. The fast-path replay
fires only on SENT; a duplicate that lands on a PENDING record re-drives the
send, which covers a crash between the PENDING write and the enqueue (a duplicate
after send-but-before-SENT re-enqueues once, tolerated by the at-least-once
pipeline). The DynamoDB record is a short-lived dedup cache (TTL); Component D's
S3 Object Lock write is the canonical audit record.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

# Clients are hoisted to module scope for warm-container reuse (DEC-2 accepts
# cold-start latency, but there is no reason to rebuild clients per invocation).
# Tests reset these to None so each moto mock is honored.
_dynamodb = None
_sqs = None


def _table():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(os.environ["IDEMPOTENCY_TABLE"])


def _sqs_client():
    global _sqs
    if _sqs is None:
        _sqs = boto3.client("sqs")
    return _sqs


def _response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            # CORS for the browser console (v1.4.0); SigV4 requests aren't
            # cookie-credentialed, so echoing the configured origin is sufficient.
            "Access-Control-Allow-Origin": os.environ.get("CONSOLE_ORIGIN", "*"),
        },
        "body": json.dumps(payload),
    }


def _caller_identity(event: dict[str, Any]) -> str:
    # Stable per-user id for segregation of duties (v2.0.0). Cognito-federated
    # console callers carry a cognitoIdentityId; a plain assumed-role caller
    # (e.g. the payment-submitter test role) falls back to its role ARN.
    ident = (event.get("requestContext") or {}).get("identity") or {}
    return ident.get("cognitoIdentityId") or ident.get("userArn") or "unknown"


def _payee_rules() -> tuple[bool, int]:
    """Phase 2.1e (DEC-29): payee input validation, sized to the Fedwire 35-char
    beneficiary-name field. Flag-gated, default ON. Set PAYEE_VALIDATION_ENABLED=false
    to restore the pre-2.1e unbounded behavior (used by the demo to reproduce the F1
    matcher-evasion attack)."""
    enabled = os.environ.get("PAYEE_VALIDATION_ENABLED", "true").strip().lower() != "false"
    try:
        max_len = int(os.environ.get("PAYEE_MAX_LENGTH", "35"))
    except ValueError:
        max_len = 35
    return enabled, max_len


def _validate_payee(payee: Any, max_len: int) -> None:
    """Fail-closed name validation (Phase 2.1e). Bounds length to the rail spec and
    restricts to printable ASCII (0x20-0x7E). The class is ASCII-printable, NOT
    single-script: 2.1d(a) proved a single-script full-Cyrillic transliteration evades
    the matcher (cosine 0.11-0.29), so only an ASCII/Latin-script rule closes that class.

    KNOWN LIMITATION (documented, not hidden): this rejects legitimate diacritic names
    (e.g. "Jose Munoz" with accents); the lower-false-reject Latin-script+NFKC variant is
    in the threat model, not implemented here. And this does NOT close F1: an in-budget
    ASCII append still evades the matcher for short listed names (measured residual:
    75/96 entities at a 35-char cap, 2.1d). This repairs the input contract; it is not a
    complete remediation."""
    if not isinstance(payee, str) or not payee:
        raise ValueError("payee is required and must be a non-empty string")
    if len(payee) > max_len:
        raise ValueError(f"payee exceeds max length {max_len} (rail-sized name field)")
    if any(ord(c) < 0x20 or ord(c) > 0x7E for c in payee):
        raise ValueError(
            "payee must be printable ASCII (rejects non-Latin/diacritic/control characters)"
        )


def _extract_payment(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if body is None:
        raise ValueError("missing request body")
    payment = json.loads(body) if isinstance(body, str) else body
    if not isinstance(payment, dict):
        raise ValueError("body must be a JSON object")
    payment_id = payment.get("payment_id")
    if not payment_id or not isinstance(payment_id, str):
        raise ValueError("payment_id is required and must be a non-empty string")
    # Phase 2.1e: fail-closed payee validation BEFORE any enqueue, so an invalid payee is
    # never screened and never approved. Raises ValueError -> handler returns 400.
    enabled, max_len = _payee_rules()
    if enabled:
        _validate_payee(payment.get("payee"), max_len)
    return payment


def handler(event, context=None):
    # 1. Validate. API Gateway request validation is the first gate; this is
    #    defense in depth (and the path exercised by direct invokes / tests).
    try:
        payment = _extract_payment(event)
    except (ValueError, json.JSONDecodeError) as exc:
        return _response(400, {"error": "invalid_payment", "detail": str(exc)})

    payment_id = payment["payment_id"]
    table = _table()
    queue_url = os.environ["OUTPUT_QUEUE_URL"]
    ttl_days = int(os.environ.get("IDEMPOTENCY_TTL_DAYS", "7"))
    now = int(time.time())

    # 2. Claim the payment_id atomically (commitment 1). Exactly one caller can
    #    create the PENDING record; a concurrent or later duplicate is refused
    #    server-side and takes the replay / re-drive path below.
    try:
        table.put_item(
            Item={
                "payment_id": payment_id,
                "status": "PENDING",
                "received_at": now,
                "ttl": now + ttl_days * 86400,
            },
            ConditionExpression="attribute_not_exists(payment_id)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        existing = table.get_item(Key={"payment_id": payment_id}).get("Item", {})
        if existing.get("status") == "SENT":
            # True idempotent replay: return the original result, do not re-enqueue.
            return _response(200, {
                "payment_id": payment_id,
                "status": "queued",
                "message_id": existing.get("message_id"),
                "idempotent_replay": True,
            })
        # status == PENDING: a prior attempt died before the enqueue completed.
        # Fall through to (re-)send so the payment is not silently lost.

    # 3. Enqueue for screening, then commit the terminal state + message id.
    #    Stamp the submitter identity so the reviewer surface can enforce
    #    segregation of duties (an approver can't clear their own payment, v2.0.0).
    payment["submitted_by"] = _caller_identity(event)
    message_id = _sqs_client().send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(payment),
    )["MessageId"]

    table.update_item(
        Key={"payment_id": payment_id},
        UpdateExpression="SET #s = :sent, message_id = :mid",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":sent": "SENT", ":mid": message_id},
    )

    return _response(200, {
        "payment_id": payment_id,
        "status": "queued",
        "message_id": message_id,
        "idempotent_replay": False,
    })
