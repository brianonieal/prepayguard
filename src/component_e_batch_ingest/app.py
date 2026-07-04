"""Component E - Batch Ingest (v2.1.2, multi-format).

An S3 upload to the batch-imports bucket triggers this handler. It parses the
file by extension - CSV, Excel (.xlsx), or JSON; anything else is accepted but
reported "unsupported" in the summary, never silently dropped - and performs the
SAME payment-ID idempotency claim + enqueue as
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

COMPONENT_VERSION = "2.1.2"
_SEND_BATCH = 10  # SQS SendMessageBatch hard limit
_MAX_ERRORS = 50  # cap per-row errors stored in the summary (keep the item small)
_SUPPORTED = ("csv", "xlsx", "json")
_HEADER_ERR = "header must include payment_id, payee, amount (payee_tin optional)"


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
    v = cells[i] if 0 <= i < len(cells) else None
    return "" if v is None else str(v).strip()  # str(): xlsx cells arrive as numbers/None


def _header_index(header):
    idx = {c: (header.index(c) if c in header else -1)
           for c in ("payment_id", "payee", "payee_tin", "amount")}
    ok = idx["payment_id"] >= 0 and idx["payee"] >= 0 and idx["amount"] >= 0
    return idx, ok


def _build_row(payment_id, payee, tin, amount_raw, label):
    """The ONE row contract shared by every format: payment_id + payee required,
    amount numeric and >= 0, payee_tin optional. Returns (row, None) or (None, error)."""
    payment_id = "" if payment_id is None else str(payment_id).strip()
    payee = "" if payee is None else str(payee).strip()
    if not payment_id or not payee:
        return None, f"{label}: payment_id and payee are required"
    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return None, f"{label}: invalid amount"
    if amount < 0:
        return None, f"{label}: invalid amount"
    row = {"payment_id": payment_id, "payee": payee, "amount": amount}
    tin = "" if tin is None else str(tin).strip()
    if tin:
        row["payee_tin"] = tin
    return row, None


def _rows_from_records(records, idx, label_of):
    """Apply _build_row across an iterable of (n, positional-cell-tuple) - CSV/XLSX."""
    rows, errors = [], []
    for n, cells in records:
        if cells is None or not any(str(c).strip() for c in cells if c is not None):
            continue  # blank line
        row, err = _build_row(_cell(cells, idx["payment_id"]), _cell(cells, idx["payee"]),
                              _cell(cells, idx["payee_tin"]), _cell(cells, idx["amount"]), label_of(n))
        if err:
            errors.append(err)
        else:
            rows.append(row)
    return rows, errors


def _parse_csv(text):
    reader = csv.reader(io.StringIO(text))
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration:
        return [], ["file is empty"]
    idx, ok = _header_index(header)
    if not ok:
        return [], [_HEADER_ERR]
    return _rows_from_records(enumerate(reader, start=2), idx, lambda n: f"row {n}")


def _parse_xlsx(raw):
    import openpyxl  # lazy import: keep cold-start light for the CSV/JSON paths
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        it = wb.active.iter_rows(values_only=True)
        try:
            header = [str(h).strip().lower() if h is not None else "" for h in next(it)]
        except StopIteration:
            return [], ["file is empty"]
        idx, ok = _header_index(header)
        if not ok:
            return [], [_HEADER_ERR]
        return _rows_from_records(enumerate(it, start=2), idx, lambda n: f"row {n}")
    finally:
        wb.close()


def _parse_json(text):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], [f"invalid JSON: {exc}"]
    if isinstance(data, dict):
        data = data.get("payments", [])
    if not isinstance(data, list):
        return [], ['JSON must be an array of payment objects (or {"payments": [...]})']
    rows, errors = [], []
    for n, obj in enumerate(data, start=1):
        if not isinstance(obj, dict):
            errors.append(f"item {n}: must be an object")
            continue
        row, err = _build_row(obj.get("payment_id"), obj.get("payee"),
                              obj.get("payee_tin"), obj.get("amount"), f"item {n}")
        if err:
            errors.append(err)
        else:
            rows.append(row)
    return rows, errors


def _parse(fmt, raw):
    if fmt == "csv":
        return _parse_csv(raw.decode("utf-8", errors="replace"))
    if fmt == "xlsx":
        return _parse_xlsx(raw)
    if fmt == "json":
        return _parse_json(raw.decode("utf-8", errors="replace"))
    return [], [f"unsupported file format (supported: {', '.join(_SUPPORTED)})"]


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
    raw = _s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()
    filename = key.split("/")[-1]
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    fmt = ext if ext in _SUPPORTED else "unsupported"
    rows, errors = _parse(fmt, raw)

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
        "format": fmt,
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
