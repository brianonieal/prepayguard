"""Component F - Scheduled Feeder tests (v3.3.0).

Deterministic: mocks the USAspending fetch and uses moto for S3, so no network and no
real AWS. Pins the award->payment mapping, the deterministic id, the demo-positive
path, the graceful fetch-error skip, and that the handler writes the batch JSON where
Component E's S3 trigger will ingest it.
"""
import importlib.util
import json
from pathlib import Path

import boto3
from moto import mock_aws

ROOT = Path(__file__).resolve().parent.parent
REGION = "us-east-2"
BUCKET = "treasury-dev-batch-imports-test"


def _load():
    path = ROOT / "src" / "component_f_feeder" / "app.py"
    spec = importlib.util.spec_from_file_location("component_f_feeder_app", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_to_payment_maps_and_filters():
    f = _load()
    assert f._to_payment({"Recipient Name": "LOCKHEED MARTIN CORP", "Award ID": "X1",
                          "Award Amount": 1000.5}) == {
        "payment_id": "USASPEND-X1", "payee": "LOCKHEED MARTIN CORP", "amount": 1000.5}
    # dropped: no name, no award id, non-positive/invalid amount
    assert f._to_payment({"Recipient Name": "", "Award ID": "X1", "Award Amount": 10}) is None
    assert f._to_payment({"Recipient Name": "A", "Award ID": "", "Award Amount": 10}) is None
    assert f._to_payment({"Recipient Name": "A", "Award ID": "X", "Award Amount": -5}) is None
    assert f._to_payment({"Recipient Name": "A", "Award ID": "X", "Award Amount": None}) is None
    assert f._to_payment({"Recipient Name": "A", "Award ID": "X", "Award Amount": "oops"}) is None


def test_page_rotates_and_is_positive():
    f = _load()
    p = f._page_for_now()
    assert 1 <= p <= f._PAGE_ROTATION


def test_demo_positive_is_labeled(monkeypatch):
    f = _load()
    monkeypatch.setenv("DEMO_POSITIVE_NAME", "Globex Overseas Incorporated")
    p = f._demo_positive()
    assert p["payee"] == "Globex Overseas Incorporated"
    assert p["payment_id"].startswith("DEMO-POS-")
    assert p["amount"] > 0


def _bucket(monkeypatch):
    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
    monkeypatch.setenv("BATCH_BUCKET", BUCKET)
    return s3


def _feed_objects(s3):
    return s3.list_objects_v2(Bucket=BUCKET, Prefix="batch-imports/").get("Contents", [])


def test_handler_writes_real_feed(monkeypatch):
    f = _load()
    with mock_aws():
        s3 = _bucket(monkeypatch)
        monkeypatch.setattr(f, "_fetch_awards", lambda limit, page: [
            {"Recipient Name": "LOCKHEED MARTIN CORP", "Award ID": "A1", "Award Amount": 100},
            {"Recipient Name": "HUMANA GOVERNMENT BUSINESS INC", "Award ID": "A2", "Award Amount": 200},
        ])
        out = f.handler({})
        assert out["written"] == 2 and out["source"] == "usaspending"
        objs = _feed_objects(s3)
        assert len(objs) == 1 and objs[0]["Key"].startswith("batch-imports/feed-")
        # key shape batch-imports/{batch_id}/payments.json so Component E derives batch_id
        assert objs[0]["Key"].endswith("/payments.json")
        body = json.loads(s3.get_object(Bucket=BUCKET, Key=objs[0]["Key"])["Body"].read())
        assert [p["payee"] for p in body["payments"]] == [
            "LOCKHEED MARTIN CORP", "HUMANA GOVERNMENT BUSINESS INC"]
        assert body["payments"][0]["payment_id"] == "USASPEND-A1"  # deterministic from Award ID


def test_handler_demo_positive_flag(monkeypatch):
    f = _load()
    with mock_aws():
        s3 = _bucket(monkeypatch)
        monkeypatch.setenv("DEMO_POSITIVE_NAME", "Globex Overseas Incorporated")
        called = []
        monkeypatch.setattr(f, "_fetch_awards", lambda limit, page: called.append(1) or [])
        out = f.handler({"demo_positive": True})
        assert out["written"] == 1 and out["source"] == "demo_positive"
        assert called == []  # demo path never calls USAspending
        key = _feed_objects(s3)[0]["Key"]
        body = json.loads(s3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
        assert body["payments"][0]["payee"] == "Globex Overseas Incorporated"
        assert body["payments"][0]["payment_id"].startswith("DEMO-POS-")


def test_handler_fetch_error_writes_nothing(monkeypatch):
    f = _load()
    with mock_aws():
        s3 = _bucket(monkeypatch)

        def boom(limit, page):
            raise RuntimeError("usaspending down")
        monkeypatch.setattr(f, "_fetch_awards", boom)
        out = f.handler({})
        assert out["written"] == 0 and out["source"] == "fetch_error"  # graceful, no raise
        assert _feed_objects(s3) == []
