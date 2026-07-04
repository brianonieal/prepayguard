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
