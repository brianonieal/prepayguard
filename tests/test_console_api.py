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
            AttributeDefinitions=[{"AttributeName": "payment_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        s3 = boto3.client("s3", region_name=REGION)
        bucket = "treasury-dev-audit-test"
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})

        monkeypatch.setenv("REVIEWS_TABLE_NAME", "treasury-dev-reviews")
        monkeypatch.setenv("AUDIT_BUCKET_NAME", bucket)
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
        yield {"app": _load("console_api"), "table": table, "s3": s3, "bucket": bucket}


def _event(method, path, body=None, caller="arn:aws:sts::1:assumed-role/console-authenticated/brian"):
    return {
        "httpMethod": method, "path": path,
        "body": json.dumps(body) if body else None,
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
