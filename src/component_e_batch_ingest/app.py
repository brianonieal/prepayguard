"""Component E - Batch Ingest (v1.6.0, write-scale hardening).

An S3 upload to the batch-imports bucket triggers this handler. It parses each
CSV row and performs the SAME payment-ID idempotency claim + enqueue as
Component A (DEC-13), against the SAME idempotency table and intake queue
(DEC-16) - so a payment submitted via both the single API and a batch file
dedupes correctly. Sends are batched (SendMessageBatch, chunks of 10) for
throughput. A per-file batch summary is written to the batches table for the
console to poll.

Reprocessing safety: batch_id is derived from the S3 object key, so an S3
re-delivery of the same object overwrites the same summary (no double count),
and per-row SENT records dedupe already-enqueued rows on the retry. Rows left
PENDING by a crash mid-file are re-driven (re-sent) on reprocess, never lost -
the same PENDING->SENT discipline as Component A.
"""
from __future__ import annotations

import csv
import datetime
import io
import json
import os
import time

import boto3
from botocore.exceptions import ClientError

_dynamodb = None
_sqs = None
_s3 = None

COMPONENT_VERSION = "1.6.0"
_SEND_BATCH = 10  # SQS SendMessageBatch hard limit
_MAX_ERRORS = 50  # cap per-row errors stored in the summary (keep the item small)


def _resource():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


def _table():
    return _resource().Table(os.environ["IDEMPOTENCY_TABLE"])


def _batches_table():
    return _resource().Table(os.environ["BATCHES_TABLE"])


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


def _cell(cells, i):
    return cells[i].strip() if 0 <= i < len(cells) else ""


def _parse_rows(text: str):
    """Mirror the console CSV contract: payment_id, payee, amount required
    (payee_tin optional). Returns (valid_rows, errors)."""
    reader = csv.reader(io.StringIO(text))
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration:
        return [], ["file is empty"]
    idx = {c: (header.index(c) if c in header else -1)
           for c in ("payment_id", "payee", "payee_tin", "amount")}
    if idx["payment_id"] < 0 or idx["payee"] < 0 or idx["amount"] < 0:
        return [], ["header must include payment_id, payee, amount (payee_tin optional)"]

    rows, errors = [], []
    for line_no, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue  # skip blank lines
        payment_id = _cell(cells, idx["payment_id"])
        payee = _cell(cells, idx["payee"])
        if not payment_id or not payee:
            errors.append(f"row {line_no}: payment_id and payee are required")
            continue
        try:
            amount = float(_cell(cells, idx["amount"]))
        except ValueError:
            errors.append(f"row {line_no}: invalid amount")
            continue
        if amount < 0:
            errors.append(f"row {line_no}: invalid amount")
            continue
        row = {"payment_id": payment_id, "payee": payee, "amount": amount}
        tin = _cell(cells, idx["payee_tin"])
        if tin:
            row["payee_tin"] = tin
        rows.append(row)
    return rows, errors


def _claim(payment_id: str, ttl_days: int) -> str:
    """Atomic claim on the shared idempotency table - the same conditional-write
    state machine as Component A. Returns 'send' (new or re-drive a stranded
    PENDING) or 'duplicate' (already SENT)."""
    now = int(time.time())
    try:
        _table().put_item(
            Item={"payment_id": payment_id, "status": "PENDING",
                  "received_at": now, "ttl": now + ttl_days * 86400},
            ConditionExpression="attribute_not_exists(payment_id)",
        )
        return "send"
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        existing = _table().get_item(Key={"payment_id": payment_id}).get("Item", {})
        # SENT -> true duplicate; PENDING -> a prior attempt died before enqueue, re-drive.
        return "duplicate" if existing.get("status") == "SENT" else "send"


def _handle_object(bucket: str, key: str, ttl_days: int) -> dict:
    text = _s3_client().get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8", errors="replace")
    rows, errors = _parse_rows(text)

    to_send, duplicate, seen = [], 0, set()
    for row in rows:
        pid = row["payment_id"]
        # Intra-file dedup: a payment_id repeated within the SAME file is a
        # duplicate. (The shared-table claim can't catch it — the first
        # occurrence is still PENDING, not yet SENT, when the repeat is checked.)
        if pid in seen:
            duplicate += 1
            continue
        seen.add(pid)
        if _claim(pid, ttl_days) == "duplicate":
            duplicate += 1
        else:
            to_send.append(row)

    queued = 0
    queue_url = os.environ["OUTPUT_QUEUE_URL"]
    for i in range(0, len(to_send), _SEND_BATCH):
        chunk = to_send[i:i + _SEND_BATCH]
        resp = _sqs_client().send_message_batch(
            QueueUrl=queue_url,
            Entries=[{"Id": str(j), "MessageBody": json.dumps(r)} for j, r in enumerate(chunk)],
        )
        sent = {s["Id"]: s["MessageId"] for s in resp.get("Successful", [])}
        for j, row in enumerate(chunk):
            message_id = sent.get(str(j))
            if message_id is None:
                continue  # failed send stays PENDING -> re-driven on a later reprocess
            _table().update_item(
                Key={"payment_id": row["payment_id"]},
                UpdateExpression="SET #s = :sent, message_id = :mid",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":sent": "SENT", ":mid": message_id},
            )
            queued += 1

    # batch-imports/{batch_id}/{filename} -> the console minted batch_id at presign.
    parts = key.split("/")
    batch_id = parts[1] if len(parts) >= 3 else key
    summary = {
        "batch_id": batch_id,
        "filename": parts[-1],
        "object_key": key,
        "status": "complete",
        "total": len(rows) + len(errors),
        "queued": queued,
        "duplicate": duplicate,
        "rejected": len(errors),
        "errors": errors[:_MAX_ERRORS],
        "received_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    _batches_table().put_item(Item=summary)
    return summary


def handler(event, context=None):
    ttl_days = int(os.environ.get("IDEMPOTENCY_TTL_DAYS", "7"))
    summaries = []
    for record in event.get("Records", []):
        summaries.append(_handle_object(
            record["s3"]["bucket"]["name"],
            record["s3"]["object"]["key"],
            ttl_days,
        ))
    return {"batches": summaries}
