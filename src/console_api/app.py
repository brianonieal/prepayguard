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
_lambda = None

COMPONENT_VERSION = "3.1.0"
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


def _lambda_client():
    global _lambda
    if _lambda is None:
        _lambda = boto3.client("lambda")
    return _lambda


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


def _load_audit(payment_id: str):
    """Return (key, record) for a payment's audit record, or (None, None)."""
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
        return None, None
    body = _s3_client().get_object(Bucket=bucket, Key=key)["Body"].read()
    return key, json.loads(body)


def _get_audit(payment_id: str) -> dict:
    key, record = _load_audit(payment_id)
    if key is None:
        return _response(404, {"error": "audit_record_not_found", "payment_id": payment_id})
    return _response(200, {"key": key, "record": record})


# --- v2.3.0: LLM adjudication brief (advisory; NEVER written to the audit) -----

BRIEF_SYSTEM = (
    "You are an assistant to a U.S. Treasury Do-Not-Pay payment reviewer. Given a "
    "screening audit record, write a concise brief (<=120 words) for a human reviewer: "
    "why the payment was flagged, what the evidence shows, and a recommended action "
    "(APPROVE, REJECT, or INVESTIGATE) with a one-line rationale. Reason ONLY from the "
    "provided record - never invent names, matches, amounts, or facts not present. This "
    "brief is advisory; the human makes and owns the decision."
)


def _llm_brief(record: dict) -> str:
    decision = record.get("decision", {})
    facts = {
        "payment_id": record.get("payment_id"),
        "payee": record.get("payment", {}).get("payee"),
        "amount": record.get("payment", {}).get("amount"),
        "disposition": decision.get("disposition"),
        "risk_score": decision.get("risk_score"),
        "reasons": decision.get("reasons", []),
        "matches": record.get("evidence", {}).get("matches", []),
        "reference_list_version": record.get("provenance", {}).get("reference_list_version"),
    }
    resp = _bedrock_client().converse(
        modelId=os.environ["BRIEF_MODEL"],
        system=[{"text": BRIEF_SYSTEM}],
        messages=[{"role": "user", "content": [{"text":
            "Screening record:\n" + json.dumps(facts, default=str) + "\n\nWrite the brief."}]}],
        inferenceConfig={"maxTokens": 300, "temperature": 0.2},
    )
    return resp["output"]["message"]["content"][0]["text"].strip()


def _brief(payment_id: str) -> dict:
    _key, record = _load_audit(payment_id)
    if record is None:
        return _response(404, {"error": "audit_record_not_found", "payment_id": payment_id})
    try:
        brief = _llm_brief(record)
    except Exception as exc:  # the brief is optional - never crash the case over it
        return _response(502, {"error": "brief_unavailable", "detail": str(exc)[:200]})
    return _response(200, {"brief": brief, "model": os.environ.get("BRIEF_MODEL"),
                           "generated_at": datetime.datetime.now(datetime.UTC).isoformat()})


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
    console uploads the file there; the ObjectCreated event drives Component E,
    which parses by extension (CSV/XLSX/JSON) and reports anything else as
    unsupported (v2.1.2). Any safe filename is accepted here."""
    filename = (body.get("filename") or "").strip()
    if not filename or "/" in filename or ".." in filename:
        return _response(400, {"error": "invalid filename"})
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


# --- v2.1.0/v2.2.0: reference-data lifecycle + semantic embeddings ---------

_bedrock = None


def _bedrock_client():
    global _bedrock
    if _bedrock is None:
        _bedrock = boto3.client("bedrock-runtime")
    return _bedrock


def _embed(text, model):
    resp = _bedrock_client().invoke_model(
        modelId=model, body=json.dumps({"inputText": str(text or ""), "normalize": True}),
        accept="application/json", contentType="application/json")
    return json.loads(resp["body"].read())["embedding"]


def _strip_embeddings(doc):
    # The 1024-float vectors are for Component B (which reads S3 directly), not
    # the browser - keep the API payload lean.
    for e in doc.get("entries", []):
        e.pop("embedding", None)
        e.pop("embedding_model", None)
    return doc


def _get_reference() -> dict:
    try:
        body = _s3_client().get_object(
            Bucket=os.environ["REFERENCE_BUCKET"], Key=REFERENCE_KEY)["Body"].read()
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return _response(404, {"error": "reference_not_seeded",
                                   "detail": "run scripts/seed_reference_data.py"})
        raise
    return _response(200, _strip_embeddings(json.loads(body)))


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
        cur_threshold = current.get("semantic_threshold")
    except ClientError:
        cur_version, sources, cur_threshold = 0, {}, None

    # v2.2.0: embed each entry name (Bedrock) so Component B can semantic-match by
    # cosine over the stored vectors - no vector DB. Embeddings are versioned WITH
    # the list, so a screening's cited version pins the exact vectors used.
    model = os.environ.get("EMBED_MODEL", "amazon.titan-embed-text-v2:0")
    for e in entries:
        e["embedding"] = _embed(e["name"], model)
        e["embedding_model"] = model

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
            "semantic_threshold": body.get("semantic_threshold", cur_threshold),
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


# --- v3.5.0: in-console feed control (admin-only) ----------------------------
# The console Feed tab edits the USAspending query the feeder (Component F) runs.
# Save persists it to S3 (drives the scheduled runs); Run invokes the feeder now
# with the posted filters inline. Admin-only at both the edge (resource policy)
# and here (_is_admin), mirroring the reference-publish control.

FEED_CONFIG_KEY = "reference/feeder-config/current.json"
# Valid USAspending award_type_codes (the console maps friendly labels to these).
_VALID_AWARD_CODES = {"A", "B", "C", "D", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11"}
_FEED_DEFAULTS = {"award_type_codes": ["A", "B", "C", "D"], "time_period_days": 365, "limit": 10}


def _feed_config(event) -> dict:
    if not _is_admin(event):
        return _response(403, {"error": "admin_only", "detail": "feed configuration requires the admin role"})
    try:
        cfg = json.loads(_s3_client().get_object(
            Bucket=os.environ["REFERENCE_BUCKET"], Key=FEED_CONFIG_KEY)["Body"].read())
    except ClientError:
        cfg = dict(_FEED_DEFAULTS)
    return _response(200, {"config": cfg, "defaults": _FEED_DEFAULTS})


def _validate_feed(body):
    """Return (config, None) or (None, error). Bounds keep the feed cheap and the
    audit-record growth bounded (limit 1-100)."""
    codes = body.get("award_type_codes")
    if not isinstance(codes, list) or not codes or any(c not in _VALID_AWARD_CODES for c in codes):
        return None, "award_type_codes must be a non-empty list of valid USAspending codes"
    try:
        days, limit = int(body.get("time_period_days", 365)), int(body.get("limit", 10))
    except (TypeError, ValueError):
        return None, "time_period_days and limit must be integers"
    if not (1 <= days <= 3650) or not (1 <= limit <= 100):
        return None, "time_period_days must be 1-3650 and limit 1-100"
    return {"award_type_codes": list(codes), "time_period_days": days, "limit": limit}, None


def _save_feed_config(event, caller: str) -> dict:
    if not _is_admin(event):
        return _response(403, {"error": "admin_only", "detail": "feed configuration requires the admin role"})
    cfg, err = _validate_feed(json.loads(event.get("body") or "{}"))
    if err:
        return _response(400, {"error": "invalid_config", "detail": err})
    cfg["updated_by"] = caller
    cfg["updated_at"] = datetime.datetime.now(datetime.UTC).isoformat()
    _s3_client().put_object(Bucket=os.environ["REFERENCE_BUCKET"], Key=FEED_CONFIG_KEY,
                            Body=json.dumps(cfg).encode(), ContentType="application/json")
    return _response(200, {"status": "saved", "config": cfg})


def _run_feed(event) -> dict:
    if not _is_admin(event):
        return _response(403, {"error": "admin_only", "detail": "running the feed requires the admin role"})
    cfg, err = _validate_feed(json.loads(event.get("body") or "{}"))
    if err:
        return _response(400, {"error": "invalid_config", "detail": err})
    try:
        resp = _lambda_client().invoke(
            FunctionName=os.environ["FEEDER_FUNCTION_ARN"],
            Payload=json.dumps({"invoke_type": "on_demand", "feeder_config": cfg}).encode())
        result = json.loads(resp["Payload"].read() or "{}")
    except Exception as exc:  # the feeder is optional to reach; never 500 the console over it
        return _response(502, {"error": "feed_run_failed", "detail": str(exc)[:200]})
    return _response(200, {"status": "ran", "config": cfg, "result": result})


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
    return _response(200, _strip_embeddings(json.loads(body)))


# --- v2.4.0: analytics & compliance reporting (admin + read-only auditor) -----

def _is_admin_or_auditor(event) -> bool:
    arn = ((event.get("requestContext") or {}).get("identity") or {}).get("userArn") or ""
    parts = arn.split("/")
    if not (len(parts) >= 2 and parts[0].endswith(":assumed-role")):
        return False
    return parts[1] in (os.environ.get("ADMIN_ROLE_NAME", ""), os.environ.get("AUDITOR_ROLE_NAME", ""))


def _scan_all(table, cap=10000):
    resp = table.scan()
    items = resp.get("Items", [])
    while resp.get("LastEvaluatedKey") and len(items) < cap:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items += resp.get("Items", [])
    return items


def _compute_summary(index_items=None) -> dict:
    """Pipeline-wide aggregate (mix / hit-rate / throughput / queue / reviewer
    productivity) over audit_index + reviews. Shared by /analytics and /showcase
    so both report identical numbers. Scan-based - fine at course scale; a
    materialized rollup is the follow-on for production volumes. Callers that have
    already scanned audit_index (e.g. /showcase) pass index_items to avoid a second
    full scan of the same table."""
    if index_items is None:
        index_items = _scan_all(_resource().Table(os.environ["AUDIT_INDEX_TABLE"]))
    mix = {"approve": 0, "review": 0, "reject": 0}
    by_day = {}
    for it in index_items:
        d = it.get("disposition")
        if d in mix:
            mix[d] += 1
        day = str(it.get("audited_at", ""))[:10]
        if day:
            by_day[day] = by_day.get(day, 0) + 1
    total = len(index_items)
    flagged = mix["review"] + mix["reject"]
    hit_rate = round(100 * flagged / total, 1) if total else 0.0
    throughput = sorted(({"day": k, "count": v} for k, v in by_day.items()), key=lambda x: x["day"])[-14:]

    review_items = _scan_all(_table())
    pending = [r for r in review_items if r.get("status") == "pending"]
    avg_score = round(sum(float(r.get("score", 0)) for r in pending) / len(pending)) if pending else 0
    oldest = min((str(r.get("received_at", "")) for r in pending), default="")
    reviewers = {}
    for r in review_items:
        if r.get("status") in ("approved", "rejected") and r.get("decided_by"):
            reviewers[r["decided_by"]] = reviewers.get(r["decided_by"], 0) + 1
    productivity = sorted(({"reviewer": k, "decisions": v} for k, v in reviewers.items()),
                          key=lambda x: -x["decisions"])
    return {
        "total_screened": total, "disposition_mix": mix, "hit_rate": hit_rate,
        "throughput": throughput,
        "queue": {"pending": len(pending), "avg_pending_score": avg_score, "oldest_pending": oldest},
        "reviewer_productivity": productivity,
    }


def _analytics(event) -> dict:
    if not _is_admin_or_auditor(event):
        return _response(403, {"error": "admin_or_auditor_only"})
    return _response(200, _compute_summary())


def _audit_log(event) -> dict:
    if not _is_admin_or_auditor(event):
        return _response(403, {"error": "admin_or_auditor_only"})
    params = event.get("queryStringParameters") or {}
    disp = params.get("disposition")
    try:
        limit = max(1, min(int(params.get("limit", 100)), 500))
    except (TypeError, ValueError):
        limit = 100
    items = _scan_all(_resource().Table(os.environ["AUDIT_INDEX_TABLE"]))
    if disp and disp != "all":
        items = [i for i in items if i.get("disposition") == disp]
    items.sort(key=lambda i: str(i.get("audited_at", "")), reverse=True)
    rows = [{"payment_id": i.get("payment_id"), "disposition": i.get("disposition"),
             "audited_at": i.get("audited_at"), "key": i.get("audit_key")} for i in items[:limit]]
    return _response(200, {"entries": rows, "count": len(rows), "truncated": len(items) > limit})


# --- v3.0.0: executive showcase (the narrative "Overview" tab) -----------------
# One lean read that feeds the whole story page: the shared summary, a match-type
# tally, and one real worked example per disposition. Match-types + examples come
# from the FULL match detail, which lives only in the S3 audit records (audit_index
# carries disposition, not the match reasons) - so we sample the most recent N and
# read those records. Bounded on purpose; visible to reviewer/admin/auditor (the
# edge already blocks submitters from non-batch console routes).

SHOWCASE_SAMPLE = 40


def _primary_match_type(record: dict) -> str:
    matches = (record.get("evidence") or {}).get("matches") or []
    if not matches:
        return "none"
    top = max(matches, key=lambda m: m.get("confidence", 0))
    return top.get("matched_on") or "none"


def _example(record: dict) -> dict:
    dec = record.get("decision") or {}
    pay = record.get("payment") or {}
    matches = (record.get("evidence") or {}).get("matches") or []
    return {
        "payment_id": record.get("payment_id"),
        "payee": pay.get("payee"),
        "amount": pay.get("amount"),
        "disposition": dec.get("disposition"),
        "risk_score": dec.get("risk_score"),
        "reasons": dec.get("reasons", []),
        "matches": [{"matched_on": m.get("matched_on"), "source": m.get("source"),
                     "severity": m.get("severity"), "confidence": m.get("confidence"),
                     "similarity": m.get("similarity")} for m in matches],
        "reference_list_version": (record.get("provenance") or {}).get("reference_list_version"),
    }


def _load_audit_record(key: str) -> dict:
    body = _s3_client().get_object(Bucket=os.environ["AUDIT_BUCKET_NAME"], Key=key)["Body"].read()
    return json.loads(body)


def _showcase(event) -> dict:
    # Scan audit_index ONCE and reuse it for the summary (avoids a second full scan).
    index = _scan_all(_resource().Table(os.environ["AUDIT_INDEX_TABLE"]))
    full = _compute_summary(index_items=index)
    # /showcase is visible to reviewers, so return ONLY the non-sensitive fields the
    # Overview page renders. reviewer_productivity (per-reviewer identities + counts)
    # and internal queue detail stay behind the admin/auditor-gated /analytics.
    summary = {
        "total_screened": full["total_screened"],
        "disposition_mix": full["disposition_mix"],
        "hit_rate": full["hit_rate"],
        "queue": {"pending": full["queue"]["pending"]},
    }
    index.sort(key=lambda i: str(i.get("audited_at", "")), reverse=True)

    match_types, examples, counted = {}, {}, 0
    for it in index[:SHOWCASE_SAMPLE]:
        key = it.get("audit_key")
        if not key:
            continue
        # A single unreadable OR malformed audit object must not break the whole page:
        # skip it. Catches ClientError (S3) and JSON/decode errors alike.
        try:
            rec = _load_audit_record(key)
            mt = _primary_match_type(rec)
        except Exception:  # noqa: BLE001 - one bad record should never 500 the Overview
            continue
        match_types[mt] = match_types.get(mt, 0) + 1
        counted += 1
        disp = (rec.get("decision") or {}).get("disposition")
        if disp in ("approve", "review", "reject") and disp not in examples:
            examples[disp] = _example(rec)

    # If a disposition never appeared in the recent sample (e.g. rejects are rare),
    # backfill one from the full index so all three worked examples always render.
    for disp in ("approve", "review", "reject"):
        if disp in examples:
            continue
        hit = next((i for i in index if i.get("disposition") == disp and i.get("audit_key")), None)
        if hit:
            try:
                examples[disp] = _example(_load_audit_record(hit["audit_key"]))
            except Exception:  # noqa: BLE001
                pass

    return _response(200, {
        "summary": summary,
        "match_types": match_types,
        "match_sample_size": counted,  # the number actually tallied, not the sample cap
        "examples": examples,
    })


# --- v3.1.0: demo reset (admin-only; clear all uploaded records for a clean demo) ---
# Clears the four DynamoDB tables that drive the console's views AND the uploaded
# files (batch-import uploads + case-document attachments) so a demo starts from a
# truly clean slate. The immutable S3 AUDIT records (Object Lock) are intentionally
# NEVER touched - by design they cannot be deleted by anyone, which is the compliance
# guarantee. Repeatable; returns per-target counts and any per-target errors.

RESET_TABLE_ENVS = ["REVIEWS_TABLE_NAME", "AUDIT_INDEX_TABLE", "BATCHES_TABLE", "IDEMPOTENCY_TABLE"]
# (env var, key prefix) for the uploaded-file buckets the reset also clears. NOT the
# audit bucket - that one is Object Lock and must survive.
RESET_UPLOAD_BUCKETS = [("BATCH_BUCKET", "batch-imports/"), ("UPLOADS_BUCKET_NAME", "cases/")]


def _clear_table(table) -> int:
    """Delete every item from a table, keyed generically off its own key schema
    (so it works regardless of the key attribute names). Paginates + batch-deletes."""
    key_attrs = [k["AttributeName"] for k in table.key_schema]
    names = {f"#{i}": a for i, a in enumerate(key_attrs)}
    proj = ", ".join(names.keys())
    deleted = 0
    kwargs = {"ProjectionExpression": proj, "ExpressionAttributeNames": names}
    resp = table.scan(**kwargs)
    while True:
        with table.batch_writer() as batch:
            for it in resp.get("Items", []):
                batch.delete_item(Key={a: it[a] for a in key_attrs})
                deleted += 1
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            return deleted
        resp = table.scan(ExclusiveStartKey=lek, **kwargs)


def _clear_bucket(bucket: str, prefix: str) -> int:
    """Delete every object under a prefix (paginated, 1000-key batches)."""
    s3 = _s3_client()
    deleted = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if objs:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": objs, "Quiet": True})
            deleted += len(objs)
    return deleted


def _reset(event) -> dict:
    if not _is_admin(event):
        return _response(403, {"error": "admin_only", "detail": "reset requires the admin role"})
    body = json.loads(event.get("body") or "{}")
    if body.get("confirm") != "RESET":
        return _response(400, {"error": "confirmation_required",
                               "detail": 'send {"confirm":"RESET"} to clear all uploaded records'})
    # Per-target try/except: the wipe is not atomic, so if one target fails (IAM drift,
    # throttling) we still clear the rest and report exactly what cleared vs. errored,
    # instead of an opaque 500 that hides a half-cleared state.
    cleared, errors = {}, {}
    for env_name in RESET_TABLE_ENVS:
        name = os.environ.get(env_name)
        if not name:
            continue
        try:
            cleared[name] = _clear_table(_resource().Table(name))
        except Exception as exc:  # noqa: BLE001
            errors[name] = str(exc)[:200]
    for env_name, prefix in RESET_UPLOAD_BUCKETS:
        bucket = os.environ.get(env_name)
        if not bucket:
            continue
        try:
            cleared[f"{bucket}/{prefix}"] = _clear_bucket(bucket, prefix)
        except Exception as exc:  # noqa: BLE001
            errors[f"{bucket}/{prefix}"] = str(exc)[:200]
    code = 200 if not errors else 207
    return _response(code, {"cleared": cleared, "errors": errors, "total": sum(cleared.values()),
                            "note": "immutable S3 audit records (Object Lock) are never touched"})


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
        # v2.3.0: on-demand advisory brief (read-only; never written to the audit).
        if method == "GET" and len(parts) == 3 and parts[0] == "reviews" and parts[2] == "brief":
            return _brief(parts[1])
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
        # Analytics & compliance (v2.4.0, admin + auditor)
        if method == "GET" and parts == ["analytics"]:
            return _analytics(event)
        if method == "GET" and parts == ["audit-log"]:
            return _audit_log(event)
        # Executive showcase (v3.0.0, any signed-in reviewer/admin/auditor)
        if method == "GET" and parts == ["showcase"]:
            return _showcase(event)
        # Demo reset (v3.1.0, admin-only; clears the working tables)
        if method == "POST" and parts == ["admin", "reset"]:
            return _reset(event)
        # v3.5.0: in-console feed control (admin-only)
        if method == "GET" and parts == ["feed", "config"]:
            return _feed_config(event)
        if method == "PUT" and parts == ["feed", "config"]:
            return _save_feed_config(event, caller)
        if method == "POST" and parts == ["feed", "run"]:
            return _run_feed(event)
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
