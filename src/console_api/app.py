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
import re
import uuid

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

_dynamodb = None
_s3 = None

COMPONENT_VERSION = "2.1.0"
BULK_DECISION_MAX = 50  # cap per bulk call (API GW/Lambda time budget)
REFERENCE_KEY = "reference/current.json"
VALID_SEVERITIES = {"high", "medium", "low"}


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


def _caller_identity(event) -> str:
    # Stable per-user id for segregation of duties (v2.0.0), matching the field
    # Component A stamps as submitted_by: cognitoIdentityId for federated console
    # users, role ARN otherwise.
    ident = (event.get("requestContext") or {}).get("identity") or {}
    return ident.get("cognitoIdentityId") or ident.get("userArn") or "unknown"


def _is_admin(event) -> bool:
    # v2.1.0: reference publishes are admin-only. The assumed-role session ARN is
    # arn:aws:sts::acct:assumed-role/ROLE_NAME/session — compare ROLE_NAME to the
    # admin role Terraform injected. (The edge also denies the reviewer role on
    # PUT /reference; this is the matching app-layer check.)
    arn = ((event.get("requestContext") or {}).get("identity") or {}).get("userArn") or ""
    admin_role = os.environ.get("ADMIN_ROLE_NAME", "")
    parts = arn.split("/")
    return bool(admin_role) and len(parts) >= 2 and parts[0].endswith(":assumed-role") and parts[1] == admin_role


def _response(code: int, payload) -> dict:
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": "application/json",
            # SPA origin (CloudFront) — SigV4-signed browser calls still need CORS.
            "Access-Control-Allow-Origin": os.environ.get("CONSOLE_ORIGIN", "*"),
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS",
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
    # Segregation of duties (v2.0.0): an approver cannot decide a payment they
    # themselves submitted. The IAM edge already stops a submitter from reaching
    # this route at all; this is the per-payment maker/checker control.
    if existing.get("submitted_by") and existing["submitted_by"] == caller_arn:
        return 403, {"payment_id": payment_id, "error": "segregation_of_duties",
                     "detail": "an approver cannot decide a payment they submitted"}

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


# --- v2.1.0: reference-data lifecycle -------------------------------------

def _get_reference() -> dict:
    try:
        body = _s3_client().get_object(
            Bucket=os.environ["REFERENCE_BUCKET"], Key=REFERENCE_KEY)["Body"].read()
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return _response(404, {"error": "reference_not_seeded",
                                   "detail": "run scripts/seed_reference_data.py"})
        raise
    return _response(200, json.loads(body))


def _validate_entries(entries) -> list[str]:
    if not isinstance(entries, list) or not entries:
        return ["entries must be a non-empty list"]
    errors = []
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            errors.append(f"entry {i}: must be an object")
            continue
        if not str(e.get("name") or "").strip():
            errors.append(f"entry {i}: name is required")
        tin = re.sub(r"\D", "", str(e.get("tin") or ""))
        if (e.get("tin") or "") and len(tin) != 9:
            errors.append(f"entry {i}: tin must be blank or 9 digits")
        if not str(e.get("source") or "").strip():
            errors.append(f"entry {i}: source is required")
        if e.get("severity") not in VALID_SEVERITIES:
            errors.append(f"entry {i}: severity must be one of high|medium|low")
    return errors


def _put_reference(event, caller: str) -> dict:
    if not _is_admin(event):
        return _response(403, {"error": "admin_only",
                               "detail": "publishing screening lists requires the admin role"})
    body = json.loads(event.get("body") or "{}")
    entries = body.get("entries")
    errors = _validate_entries(entries)
    if errors:
        return _response(400, {"error": "invalid_entries", "detail": errors})

    bucket = os.environ["REFERENCE_BUCKET"]
    s3 = _s3_client()
    try:
        current = json.loads(s3.get_object(Bucket=bucket, Key=REFERENCE_KEY)["Body"].read())
        cur_version, sources = int(current.get("version", 0)), current.get("sources", {})
    except ClientError:
        cur_version, sources = 0, {}

    # Claim the next version number with a conditional put (If-None-Match) so two
    # concurrent publishes can never mint the same immutable versions/{N}.json.
    doc = None
    for attempt in range(3):
        n = cur_version + 1 + attempt
        doc = {
            "version": n,
            "updated_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "updated_by": caller,
            "sources": body.get("sources", sources),
            "entries": entries,
        }
        try:
            s3.put_object(Bucket=bucket, Key=f"reference/versions/{n}.json",
                          Body=json.dumps(doc).encode(), ContentType="application/json",
                          IfNoneMatch="*")
            break
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in ("PreconditionFailed", "412"):
                raise
    else:
        return _response(409, {"error": "publish_conflict", "detail": "concurrent publishes; retry"})

    # History claimed; now flip the active pointer. B's TTL cache picks it up
    # within REFERENCE_TTL_SECONDS.
    s3.put_object(Bucket=bucket, Key=REFERENCE_KEY,
                  Body=json.dumps(doc).encode(), ContentType="application/json")
    return _response(200, {"version": doc["version"], "entry_count": len(entries),
                           "updated_by": caller})


def _list_reference_versions() -> dict:
    resp = _s3_client().list_objects_v2(
        Bucket=os.environ["REFERENCE_BUCKET"], Prefix="reference/versions/")
    versions = []
    for o in resp.get("Contents", []):
        m = re.fullmatch(r"reference/versions/(\d+)\.json", o["Key"])
        if m:
            versions.append({"version": int(m.group(1)),
                             "published_at": o["LastModified"].isoformat(),
                             "size": o["Size"]})
    versions.sort(key=lambda v: v["version"], reverse=True)
    return _response(200, {"versions": versions, "count": len(versions)})


def _get_reference_version(n: str) -> dict:
    if not n.isdigit():
        return _response(400, {"error": "version must be an integer"})
    try:
        body = _s3_client().get_object(
            Bucket=os.environ["REFERENCE_BUCKET"], Key=f"reference/versions/{int(n)}.json")["Body"].read()
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return _response(404, {"error": "version_not_found", "version": int(n)})
        raise
    return _response(200, json.loads(body))


def handler(event, context=None):
    method = event.get("httpMethod", "")
    path = event.get("path", "")
    parts = [p for p in path.split("/") if p]
    caller = _caller_identity(event)

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
        # Reference-data lifecycle (v2.1.0)
        if method == "GET" and parts == ["reference"]:
            return _get_reference()
        if method == "PUT" and parts == ["reference"]:
            return _put_reference(event, caller)
        if method == "GET" and parts == ["reference", "versions"]:
            return _list_reference_versions()
        if method == "GET" and len(parts) == 3 and parts[0] == "reference" and parts[1] == "versions":
            return _get_reference_version(parts[2])
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
