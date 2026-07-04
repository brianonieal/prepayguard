"""Console read/action API (v1.2.0) — list / audit fetch / reviewer decision."""
import json

import boto3
import pytest
from moto import mock_aws

REGION = "us-east-2"


@pytest.fixture
def console_api(monkeypatch):
    from conftest import _load
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=REGION)
        table = ddb.create_table(
            TableName="treasury-dev-reviews",
            KeySchema=[{"AttributeName": "payment_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "payment_id", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "received_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "status-received_at-index",
                "KeySchema": [
                    {"AttributeName": "status", "KeyType": "HASH"},
                    {"AttributeName": "received_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )
        index = ddb.create_table(
            TableName="treasury-dev-audit-index",
            KeySchema=[{"AttributeName": "payment_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "payment_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        batches = ddb.create_table(  # v1.6.0 batch summary table
            TableName="treasury-dev-batches",
            KeySchema=[{"AttributeName": "batch_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "batch_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        s3 = boto3.client("s3", region_name=REGION)
        bucket = "treasury-dev-audit-test"
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})

        uploads = "treasury-dev-console-uploads-test"
        s3.create_bucket(Bucket=uploads, CreateBucketConfiguration={"LocationConstraint": REGION})
        batch_bucket = "treasury-dev-batch-imports-test"
        s3.create_bucket(Bucket=batch_bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
        reference_bucket = "treasury-dev-reference-test"  # v2.1.0
        s3.create_bucket(Bucket=reference_bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
        seed = json.dumps({"version": 1, "updated_at": "2026-07-04T00:00:00+00:00",
                           "updated_by": "seed", "sources": {"sam_exclusions": "test"},
                           "entries": [{"name": "Acme Shell LLC", "tin": "900000002",
                                        "source": "sam_exclusions", "severity": "high"}]}).encode()
        s3.put_object(Bucket=reference_bucket, Key="reference/current.json", Body=seed)
        s3.put_object(Bucket=reference_bucket, Key="reference/versions/1.json", Body=seed)
        monkeypatch.setenv("REFERENCE_BUCKET", reference_bucket)
        monkeypatch.setenv("ADMIN_ROLE_NAME", "treasury-dev-console-admin")
        monkeypatch.setenv("REVIEWS_TABLE_NAME", "treasury-dev-reviews")
        monkeypatch.setenv("AUDIT_BUCKET_NAME", bucket)
        monkeypatch.setenv("AUDIT_INDEX_TABLE", "treasury-dev-audit-index")
        monkeypatch.setenv("UPLOADS_BUCKET_NAME", uploads)
        monkeypatch.setenv("BATCH_BUCKET", batch_bucket)
        monkeypatch.setenv("BATCHES_TABLE", "treasury-dev-batches")
        monkeypatch.setenv("CONSOLE_ORIGIN", "https://console.example.test")

        table.put_item(Item={
            "payment_id": "r1", "audit_id": "a-111", "score": 60,
            "status": "pending", "received_at": "2026-07-03T20:00:00+00:00",
        })
        s3.put_object(
            Bucket=bucket,
            Key="audit/2026/07/03/r1-a-111.json",
            Body=json.dumps({"audit_id": "a-111", "payment_id": "r1",
                             "decision": {"disposition": "review"}}).encode(),
        )
        app = _load("console_api")
        # v2.2.0: publish embeds entries via Bedrock; stub it (no live model in tests).
        monkeypatch.setattr(app, "_embed", lambda text, model: [0.1, 0.2, 0.3, 0.4])
        yield {"app": app, "table": table, "index": index, "batches": batches,
               "s3": s3, "bucket": bucket, "uploads": uploads, "batch_bucket": batch_bucket,
               "reference_bucket": reference_bucket}


def _event(method, path, body=None, qs=None, caller="arn:aws:sts::1:assumed-role/console-authenticated/brian"):
    return {
        "httpMethod": method, "path": path,
        "body": json.dumps(body) if body else None,
        "queryStringParameters": qs,
        "requestContext": {"identity": {"userArn": caller}},
    }


def test_list_reviews(console_api):
    resp = console_api["app"].handler(_event("GET", "/reviews"))
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["count"] == 1 and body["reviews"][0]["payment_id"] == "r1"
    assert resp["headers"]["Access-Control-Allow-Origin"] == "https://console.example.test"


def test_get_audit_record(console_api):
    resp = console_api["app"].handler(_event("GET", "/audit/r1"))
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["record"]["audit_id"] == "a-111"


def test_get_audit_unknown_payment_404(console_api):
    assert console_api["app"].handler(_event("GET", "/audit/nope"))["statusCode"] == 404


def test_decision_flips_status_and_writes_decision_audit(console_api):
    resp = console_api["app"].handler(
        _event("POST", "/reviews/r1/decision", body={"decision": "approved", "note": "verified vendor"}))
    assert resp["statusCode"] == 200
    item = console_api["table"].get_item(Key={"payment_id": "r1"})["Item"]
    assert item["status"] == "approved"
    assert item["decided_by"].endswith("/brian")
    # The reviewer's decision is itself audited (Object Lock bucket).
    keys = [o["Key"] for o in console_api["s3"].list_objects_v2(
        Bucket=console_api["bucket"], Prefix="audit/")["Contents"]]
    assert any(k.split("/")[-1].startswith("decision-r1-") for k in keys)


def test_decision_on_decided_item_409(console_api):
    app = console_api["app"]
    app.handler(_event("POST", "/reviews/r1/decision", body={"decision": "rejected"}))
    resp = app.handler(_event("POST", "/reviews/r1/decision", body={"decision": "approved"}))
    assert resp["statusCode"] == 409


def test_invalid_decision_400(console_api):
    resp = console_api["app"].handler(
        _event("POST", "/reviews/r1/decision", body={"decision": "maybe"}))
    assert resp["statusCode"] == 400


def test_presign_attachment_returns_upload_url(console_api):
    resp = console_api["app"].handler(
        _event("POST", "/reviews/r1/attachments", body={"filename": "evidence.pdf", "content_type": "application/pdf"}))
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["key"] == "cases/r1/evidence.pdf"
    assert "X-Amz-Signature" in body["upload_url"]


def test_presign_rejects_bad_filename(console_api):
    resp = console_api["app"].handler(
        _event("POST", "/reviews/r1/attachments", body={"filename": "../../etc/passwd"}))
    assert resp["statusCode"] == 400


def test_list_attachments(console_api):
    console_api["s3"].put_object(Bucket=console_api["uploads"], Key="cases/r1/note.pdf", Body=b"x")
    resp = console_api["app"].handler(_event("GET", "/reviews/r1/attachments"))
    body = json.loads(resp["body"])
    assert body["count"] == 1 and body["attachments"][0]["name"] == "note.pdf"


def test_reviews_paginated_by_status(console_api):
    # v1.5.0: GSI query by status, paginated with a cursor round-trip.
    app, t = console_api["app"], console_api["table"]
    for i in range(3):
        t.put_item(Item={"payment_id": f"pg{i}", "status": "pending",
                         "received_at": f"2026-07-0{i + 1}T00:00:00+00:00", "score": 50, "payee": "X", "audit_id": "a"})
    p1 = json.loads(app.handler(_event("GET", "/reviews", qs={"status": "pending", "limit": "2"}))["body"])
    assert len(p1["reviews"]) == 2 and p1["next_cursor"]
    p2 = json.loads(app.handler(_event("GET", "/reviews", qs={"status": "pending", "limit": "2", "cursor": p1["next_cursor"]}))["body"])
    assert len(p2["reviews"]) >= 1
    ids1 = {r["payment_id"] for r in p1["reviews"]}
    ids2 = {r["payment_id"] for r in p2["reviews"]}
    assert ids1.isdisjoint(ids2)  # no overlap across pages


def test_get_audit_uses_index(console_api):
    # v1.5.0: index hit → O(1), no prefix scan.
    console_api["index"].put_item(Item={"payment_id": "r1", "audit_key": "audit/2026/07/03/r1-a-111.json"})
    resp = console_api["app"].handler(_event("GET", "/audit/r1"))
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200 and body["key"] == "audit/2026/07/03/r1-a-111.json"


def test_get_audit_falls_back_without_index(console_api):
    # No index entry → prefix-scan fallback still finds it (backward compat).
    resp = console_api["app"].handler(_event("GET", "/audit/r1"))
    assert resp["statusCode"] == 200


# --- v2.3.0: advisory LLM adjudication brief ---

def test_brief_returns_grounded_summary(console_api, monkeypatch):
    captured = {}

    def fake(record):
        captured["record"] = record
        return "Flagged on a name match to a treasury_offset entry. Recommend INVESTIGATE."
    monkeypatch.setattr(console_api["app"], "_llm_brief", fake)  # no live Bedrock in tests
    resp = console_api["app"].handler(_event("GET", "/reviews/r1/brief"))
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200 and "INVESTIGATE" in body["brief"]
    # grounded in the ACTUAL audit record (disposition comes from r1's record)
    assert captured["record"]["decision"]["disposition"] == "review"


def test_brief_404_when_no_audit_record(console_api):
    assert console_api["app"].handler(_event("GET", "/reviews/ghost/brief"))["statusCode"] == 404


def test_brief_degrades_gracefully_on_model_error(console_api, monkeypatch):
    def boom(record):
        raise RuntimeError("bedrock throttled")
    monkeypatch.setattr(console_api["app"], "_llm_brief", boom)
    resp = console_api["app"].handler(_event("GET", "/reviews/r1/brief"))
    assert resp["statusCode"] == 502 and json.loads(resp["body"])["error"] == "brief_unavailable"


# --- v1.6.0 write-scale: batch ingestion + bulk decisions ---

def test_presign_batch_returns_upload_url(console_api):
    resp = console_api["app"].handler(_event("POST", "/batches", body={"filename": "payroll.csv"}))
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["batch_id"] and body["key"] == f"batch-imports/{body['batch_id']}/payroll.csv"
    assert "X-Amz-Signature" in body["upload_url"]


def test_presign_batch_accepts_any_safe_filename(console_api):
    # v2.1.2: CSV/XLSX/JSON (and anything) presign; Component E decides format.
    for name in ("payroll.xlsx", "vendors.json", "data.csv", "scan.pdf"):
        r = console_api["app"].handler(_event("POST", "/batches", body={"filename": name}))
        assert r["statusCode"] == 200 and json.loads(r["body"])["key"].endswith(name)
    # path-traversal is still rejected
    bad = console_api["app"].handler(_event("POST", "/batches", body={"filename": "../etc/passwd"}))
    assert bad["statusCode"] == 400


def test_get_batch_processing_then_complete(console_api):
    app = console_api["app"]
    # Before E writes the summary, the poller is told to keep waiting.
    pending = json.loads(app.handler(_event("GET", "/batches/b-xyz"))["body"])
    assert pending["status"] == "processing"
    console_api["batches"].put_item(Item={
        "batch_id": "b-xyz", "filename": "payroll.csv", "status": "complete",
        "total": 3, "queued": 2, "duplicate": 1, "rejected": 0, "received_at": "2026-07-04T10:00:00+00:00",
    })
    done = json.loads(app.handler(_event("GET", "/batches/b-xyz"))["body"])
    # DynamoDB numbers serialize to strings via the app's default=str (same as `score`).
    assert done["status"] == "complete" and int(done["queued"]) == 2 and int(done["duplicate"]) == 1


def test_list_batches_newest_first(console_api):
    for i in range(2):
        console_api["batches"].put_item(Item={
            "batch_id": f"b{i}", "filename": f"f{i}.csv", "status": "complete",
            "total": 1, "queued": 1, "duplicate": 0, "rejected": 0,
            "received_at": f"2026-07-0{i + 1}T00:00:00+00:00",
        })
    body = json.loads(console_api["app"].handler(_event("GET", "/batches"))["body"])
    assert body["count"] == 2 and body["batches"][0]["batch_id"] == "b1"  # newest first


def test_bulk_decide_applies_each_and_audits(console_api):
    app, t = console_api["app"], console_api["table"]
    t.put_item(Item={"payment_id": "r2", "audit_id": "a-222", "score": 55,
                     "status": "pending", "received_at": "2026-07-03T21:00:00+00:00"})
    resp = app.handler(_event("POST", "/reviews/decisions",
                              body={"payment_ids": ["r1", "r2"], "decision": "approved", "note": "cleared"}))
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200 and body["applied"] == 2
    assert t.get_item(Key={"payment_id": "r1"})["Item"]["status"] == "approved"
    assert t.get_item(Key={"payment_id": "r2"})["Item"]["status"] == "approved"
    # Each payment gets its own decision audit record.
    keys = [o["Key"] for o in console_api["s3"].list_objects_v2(
        Bucket=console_api["bucket"], Prefix="audit/")["Contents"]]
    assert any("decision-r1-" in k for k in keys) and any("decision-r2-" in k for k in keys)


def test_bulk_decide_partial_failure_reported(console_api):
    resp = console_api["app"].handler(_event("POST", "/reviews/decisions",
                                             body={"payment_ids": ["r1", "ghost"], "decision": "rejected"}))
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200 and body["applied"] == 1
    by_id = {r["payment_id"]: r for r in body["results"]}
    assert by_id["r1"]["ok"] is True and by_id["ghost"]["ok"] is False


def test_bulk_decide_caps_batch_size(console_api):
    resp = console_api["app"].handler(_event("POST", "/reviews/decisions",
                                             body={"payment_ids": [f"p{i}" for i in range(51)], "decision": "approved"}))
    assert resp["statusCode"] == 400


# --- v2.1.0 reference-data lifecycle ---

ADMIN = "arn:aws:sts::1:assumed-role/treasury-dev-console-admin/brian"
REVIEWER = "arn:aws:sts::1:assumed-role/treasury-dev-console-reviewer/kim"
NEW_ENTRIES = [
    {"name": "Acme Shell LLC", "tin": "900000002", "source": "sam_exclusions", "severity": "high"},
    {"name": "Fresh Fraud Front LLC", "tin": "900000042", "source": "sam_exclusions", "severity": "high"},
]


def test_get_reference_returns_current_version(console_api):
    body = json.loads(console_api["app"].handler(_event("GET", "/reference"))["body"])
    assert body["version"] == 1 and len(body["entries"]) == 1


def test_admin_publish_bumps_version_and_keeps_history(console_api):
    app = console_api["app"]
    resp = app.handler(_event("PUT", "/reference", body={"entries": NEW_ENTRIES}, caller=ADMIN))
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["version"] == 2
    # current.json is now v2, stamped with the publisher...
    cur = json.loads(console_api["s3"].get_object(
        Bucket=console_api["reference_bucket"], Key="reference/current.json")["Body"].read())
    assert cur["version"] == 2 and cur["updated_by"] == ADMIN and len(cur["entries"]) == 2
    # ...and v1 remains resolvable (the audit-citation target).
    v1 = json.loads(app.handler(_event("GET", "/reference/versions/1"))["body"])
    assert v1["version"] == 1 and len(v1["entries"]) == 1


def test_reviewer_publish_403(console_api):
    resp = console_api["app"].handler(
        _event("PUT", "/reference", body={"entries": NEW_ENTRIES}, caller=REVIEWER))
    assert resp["statusCode"] == 403
    assert json.loads(resp["body"])["error"] == "admin_only"


def test_publish_validates_entries(console_api):
    bad = [{"name": "", "tin": "12345", "source": "", "severity": "extreme"}]
    resp = console_api["app"].handler(_event("PUT", "/reference", body={"entries": bad}, caller=ADMIN))
    assert resp["statusCode"] == 400
    detail = json.loads(resp["body"])["detail"]
    assert len(detail) == 4  # name, tin, source, severity all flagged


def test_publish_embeds_entries_and_get_strips_them(console_api):
    # v2.2.0: publish stores per-entry embeddings; the API GET hides them.
    app = console_api["app"]
    app.handler(_event("PUT", "/reference", body={"entries": NEW_ENTRIES}, caller=ADMIN))
    stored = json.loads(console_api["s3"].get_object(
        Bucket=console_api["reference_bucket"], Key="reference/current.json")["Body"].read())
    assert all("embedding" in e for e in stored["entries"])          # in the store (for B)
    got = json.loads(app.handler(_event("GET", "/reference"))["body"])
    assert all("embedding" not in e for e in got["entries"])         # stripped for the browser


def test_version_history_lists_newest_first(console_api):
    app = console_api["app"]
    app.handler(_event("PUT", "/reference", body={"entries": NEW_ENTRIES}, caller=ADMIN))
    body = json.loads(app.handler(_event("GET", "/reference/versions"))["body"])
    assert [v["version"] for v in body["versions"]] == [2, 1]
    assert app.handler(_event("GET", "/reference/versions/9"))["statusCode"] == 404


# --- v2.0.0 segregation of duties ---

CALLER = "arn:aws:sts::1:assumed-role/console-authenticated/brian"


def _pending(payment_id, submitted_by):
    return {"payment_id": payment_id, "audit_id": "a", "status": "pending",
            "received_at": "2026-07-04T00:00:00+00:00", "submitted_by": submitted_by}


def test_sod_blocks_self_approval(console_api):
    console_api["table"].put_item(Item=_pending("own1", CALLER))  # submitted by the same identity
    resp = console_api["app"].handler(_event("POST", "/reviews/own1/decision", body={"decision": "approved"}, caller=CALLER))
    assert resp["statusCode"] == 403
    assert json.loads(resp["body"])["error"] == "segregation_of_duties"
    assert console_api["table"].get_item(Key={"payment_id": "own1"})["Item"]["status"] == "pending"  # untouched


def test_sod_allows_cross_identity_approval(console_api):
    console_api["table"].put_item(Item=_pending("other1", "a-different-submitter"))
    resp = console_api["app"].handler(_event("POST", "/reviews/other1/decision", body={"decision": "approved"}, caller=CALLER))
    assert resp["statusCode"] == 200


def test_bulk_decide_respects_sod(console_api):
    console_api["table"].put_item(Item=_pending("mine", CALLER))
    console_api["table"].put_item(Item=_pending("theirs", "someone-else"))
    resp = console_api["app"].handler(_event("POST", "/reviews/decisions",
                                             body={"payment_ids": ["mine", "theirs"], "decision": "approved"}, caller=CALLER))
    body = json.loads(resp["body"])
    assert body["applied"] == 1
    by_id = {r["payment_id"]: r for r in body["results"]}
    assert by_id["theirs"]["ok"] is True
    assert by_id["mine"]["ok"] is False and by_id["mine"]["error"] == "segregation_of_duties"
