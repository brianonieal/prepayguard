"""Treasury Console read/action API (v1.2.0).

One router Lambda behind an IAM-authed REST API (console authenticated role only):
  GET  /reviews                          list review items (dashboard)
  GET  /audit/{payment_id}               fetch the Object Lock audit record
  POST /reviews/{payment_id}/decision    reviewer approve/reject

Reviewer decisions are themselves audited: a decision audit record (with
integrity hash) is written to the same Object Lock bucket before the table
status flips.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import uuid

import boto3
from boto3.dynamodb.conditions import Key

_dynamodb = None
_s3 = None

COMPONENT_VERSION = "1.6.0"
BULK_DECISION_MAX = 50  # cap per bulk call (API GW/Lambda time budget)


def _resource():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


def _table():
    return _resource().Table(os.environ["REVIEWS_TABLE_NAME"])


def _s3_client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _response(code: int, payload) -> dict:
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": "application/json",
            # SPA origin (CloudFront) — SigV4-signed browser calls still need CORS.
            "Access-Control-Allow-Origin": os.environ.get("CONSOLE_ORIGIN", "*"),
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(payload, default=str),
    }


def _find_audit_key(bucket: str, payment_id: str) -> str | None:
    # Audit keys are audit/yyyy/mm/dd/{payment_id}-{audit_id}.json. Course-scale
    # prefix scan; production would index key by payment_id (follow-on note).
    paginator = _s3_client().get_paginator("list_objects_v2")
    newest = None
    for page in paginator.paginate(Bucket=bucket, Prefix="audit/"):
        for obj in page.get("Contents", []):
            if f"/{payment_id}-" in obj["Key"]:
                if newest is None or obj["LastModified"] > newest[1]:
                    newest = (obj["Key"], obj["LastModified"])
    return newest[0] if newest else None


def _list_reviews(event: dict) -> dict:
    params = event.get("queryStringParameters") or {}
    status = params.get("status")
    try:
        limit = max(1, min(int(params.get("limit", 25)), 100))
    except (TypeError, ValueError):
        limit = 25
    kwargs = {"Limit": limit}
    cursor = params.get("cursor")
    if cursor:
        try:
            kwargs["ExclusiveStartKey"] = json.loads(base64.urlsafe_b64decode(cursor))
        except Exception:
            return _response(400, {"error": "invalid cursor"})

    table = _table()
    if status and status != "all":
        # v1.5.0: query the GSI by status, newest-first — no full-table Scan.
        resp = table.query(IndexName="status-received_at-index",
                           KeyConditionExpression=Key("status").eq(status),
                           ScanIndexForward=False, **kwargs)
    else:
        resp = table.scan(**kwargs)
    items = resp.get("Items", [])
    lek = resp.get("LastEvaluatedKey")
    next_cursor = base64.urlsafe_b64encode(json.dumps(lek).encode()).decode() if lek else None
    return _response(200, {"reviews": items, "count": len(items), "next_cursor": next_cursor})


def _get_audit(payment_id: str) -> dict:
    bucket = os.environ["AUDIT_BUCKET_NAME"]
    key = None
    # v1.5.0: O(1) index lookup; fall back to the prefix scan for pre-index records.
    index_table = os.environ.get("AUDIT_INDEX_TABLE")
    if index_table:
        item = _resource().Table(index_table).get_item(Key={"payment_id": payment_id}).get("Item")
        if item:
            key = item.get("audit_key")
    if key is None:
        key = _find_audit_key(bucket, payment_id)
    if key is None:
        return _response(404, {"error": "audit_record_not_found", "payment_id": payment_id})
    body = _s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()
    return _response(200, {"key": key, "record": json.loads(body)})


def _list_attachments(payment_id: str) -> dict:
    bucket = os.environ["UPLOADS_BUCKET_NAME"]
    prefix = f"cases/{payment_id}/"
    objs = _s3_client().list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])
    files = [{
        "name": o["Key"].split("/")[-1],
        "key": o["Key"],
        "size": o["Size"],
        "uploaded_at": o["LastModified"].isoformat(),
    } for o in objs]
    return _response(200, {"attachments": files, "count": len(files)})


def _presign_attachment(payment_id: str, body: dict) -> dict:
    filename = (body.get("filename") or "").strip()
    if not filename or "/" in filename or ".." in filename:
        return _response(400, {"error": "invalid filename"})
    bucket = os.environ["UPLOADS_BUCKET_NAME"]
    key = f"cases/{payment_id}/{filename}"
    url = _s3_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": body.get("content_type", "application/octet-stream")},
        ExpiresIn=300,
    )
    return _response(200, {"upload_url": url, "key": key})


def _apply_decision(payment_id: str, decision: str, note: str, caller_arn: str):
    """Core single-payment decision: audit-first, then flip status. Returns
    (status_code, payload). Shared by the single and bulk endpoints so both
    write an identical, individually-hashed decision audit record per payment."""
    existing = _table().get_item(Key={"payment_id": payment_id}).get("Item")
    if existing is None:
        return 404, {"payment_id": payment_id, "error": "review_not_found"}
    if existing.get("status") != "pending":
        return 409, {"payment_id": payment_id, "error": "already_decided", "status": existing.get("status")}

    now = datetime.datetime.now(datetime.UTC).isoformat()
    record = {
        "schema_version": "1.0",
        "record_type": "reviewer_decision",
        "audit_id": str(uuid.uuid4()),
        "payment_id": payment_id,
        "original_audit_id": existing.get("audit_id"),
        "decision": decision,
        "note": note,
        "decided_by": caller_arn,
        "decided_at": now,
    }
    digest = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    record["integrity"] = {"algorithm": "sha256", "sha256": digest}

    # Audit-first (same ordering discipline as Component D), then flip status.
    date_path = now[:10].replace("-", "/")
    _s3_client().put_object(
        Bucket=os.environ["AUDIT_BUCKET_NAME"],
        Key=f"audit/{date_path}/decision-{payment_id}-{record['audit_id']}.json",
        Body=json.dumps(record).encode(),
        ContentType="application/json",
    )
    _table().update_item(
        Key={"payment_id": payment_id},
        UpdateExpression="SET #s = :s, decided_at = :t, decided_by = :b, decision_audit_id = :a",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": decision, ":t": now, ":b": caller_arn, ":a": record["audit_id"]},
    )
    return 200, {"payment_id": payment_id, "status": decision, "decision_audit_id": record["audit_id"]}


def _decide(payment_id: str, body: dict, caller_arn: str) -> dict:
    decision = body.get("decision")
    if decision not in ("approved", "rejected"):
        return _response(400, {"error": "decision must be 'approved' or 'rejected'"})
    code, payload = _apply_decision(payment_id, decision, body.get("note", ""), caller_arn)
    return _response(code, payload)


def _bulk_decide(body: dict, caller_arn: str) -> dict:
    """Apply one decision to many payments (v1.6.0). Each payment still gets its
    own immutable audit record; per-item outcomes are reported so a partial
    failure (already-decided, not-found) never fails the whole batch."""
    decision = body.get("decision")
    if decision not in ("approved", "rejected"):
        return _response(400, {"error": "decision must be 'approved' or 'rejected'"})
    ids = body.get("payment_ids")
    if not isinstance(ids, list) or not ids:
        return _response(400, {"error": "payment_ids must be a non-empty list"})
    if len(ids) > BULK_DECISION_MAX:
        return _response(400, {"error": "too_many", "detail": f"max {BULK_DECISION_MAX} payments per bulk decision"})

    note = body.get("note", "")
    results, applied = [], 0
    for pid in ids:
        code, payload = _apply_decision(str(pid), decision, note, caller_arn)
        if code == 200:
            applied += 1
            results.append({"payment_id": str(pid), "ok": True, "status": decision})
        else:
            results.append({"payment_id": str(pid), "ok": False, "error": payload.get("error")})
    return _response(200, {"decision": decision, "requested": len(ids), "applied": applied, "results": results})


def _presign_batch(body: dict) -> dict:
    """Mint a batch_id and a presigned PUT into the batch-imports bucket. The
    console uploads the CSV there; the ObjectCreated event drives Component E."""
    filename = (body.get("filename") or "").strip()
    if not filename or "/" in filename or ".." in filename:
        return _response(400, {"error": "invalid filename"})
    if not filename.lower().endswith(".csv"):
        return _response(400, {"error": "must be a .csv file"})
    batch_id = str(uuid.uuid4())
    key = f"batch-imports/{batch_id}/{filename}"
    url = _s3_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": os.environ["BATCH_BUCKET"], "Key": key},
        ExpiresIn=300,
    )
    return _response(200, {"upload_url": url, "batch_id": batch_id, "key": key})


def _get_batch(batch_id: str) -> dict:
    item = _resource().Table(os.environ["BATCHES_TABLE"]).get_item(Key={"batch_id": batch_id}).get("Item")
    if item is None:
        # E has not written the summary yet — tell the poller to keep waiting.
        return _response(200, {"batch_id": batch_id, "status": "processing"})
    return _response(200, item)


def _list_batches() -> dict:
    resp = _resource().Table(os.environ["BATCHES_TABLE"]).scan(Limit=25)
    items = sorted(resp.get("Items", []), key=lambda b: b.get("received_at", ""), reverse=True)
    return _response(200, {"batches": items, "count": len(items)})


def handler(event, context=None):
    method = event.get("httpMethod", "")
    path = event.get("path", "")
    parts = [p for p in path.split("/") if p]
    caller = event.get("requestContext", {}).get("identity", {}).get("userArn", "unknown")

    try:
        if method == "GET" and parts == ["reviews"]:
            return _list_reviews(event)
        if method == "GET" and len(parts) == 2 and parts[0] == "audit":
            return _get_audit(parts[1])
        # Bulk decision (v1.6.0) — checked before the single-decision route below.
        if method == "POST" and parts == ["reviews", "decisions"]:
            return _bulk_decide(json.loads(event.get("body") or "{}"), caller)
        if method == "POST" and len(parts) == 3 and parts[0] == "reviews" and parts[2] == "decision":
            return _decide(parts[1], json.loads(event.get("body") or "{}"), caller)
        if method == "GET" and len(parts) == 3 and parts[0] == "reviews" and parts[2] == "attachments":
            return _list_attachments(parts[1])
        if method == "POST" and len(parts) == 3 and parts[0] == "reviews" and parts[2] == "attachments":
            return _presign_attachment(parts[1], json.loads(event.get("body") or "{}"))
        # Batch ingestion (v1.6.0)
        if method == "POST" and parts == ["batches"]:
            return _presign_batch(json.loads(event.get("body") or "{}"))
        if method == "GET" and parts == ["batches"]:
            return _list_batches()
        if method == "GET" and len(parts) == 2 and parts[0] == "batches":
            return _get_batch(parts[1])
        return _response(404, {"error": "no_such_route", "method": method, "path": path})
    except json.JSONDecodeError:
        return _response(400, {"error": "invalid_json_body"})
