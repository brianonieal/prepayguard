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
        monkeypatch.setattr(f, "_fetch_awards", lambda config: [
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
        monkeypatch.setattr(f, "_fetch_awards", lambda config: called.append(1) or [])
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

        def boom(config):
            raise RuntimeError("usaspending down")
        monkeypatch.setattr(f, "_fetch_awards", boom)
        out = f.handler({})
        assert out["written"] == 0 and out["source"] == "fetch_error"  # graceful, no raise
        assert _feed_objects(s3) == []


# --- v3.5.0: config precedence (event > saved S3 > defaults) ---

def test_load_config_defaults(monkeypatch):
    f = _load()
    monkeypatch.setenv("FEED_LIMIT", "10")
    monkeypatch.delenv("FEEDER_CONFIG_BUCKET", raising=False)
    cfg = f._load_config({})
    assert cfg["award_type_codes"] == ["A", "B", "C", "D"]
    assert cfg["time_period_days"] == 365 and cfg["limit"] == 10


def test_load_config_inline_event_wins(monkeypatch):
    f = _load()
    cfg = f._load_config({"feeder_config": {"award_type_codes": ["02", "03"], "limit": 25}})
    assert cfg["award_type_codes"] == ["02", "03"] and cfg["limit"] == 25
    assert cfg["time_period_days"] == 365  # unspecified field keeps the default


def test_load_config_reads_saved_s3(monkeypatch):
    f = _load()
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
        s3.put_object(Bucket=BUCKET, Key="reference/feeder-config/current.json",
                      Body=json.dumps({"award_type_codes": ["07"], "time_period_days": 90, "limit": 5}).encode())
        monkeypatch.setenv("FEEDER_CONFIG_BUCKET", BUCKET)
        cfg = f._load_config({})  # scheduled run (no inline) -> reads S3
        assert cfg["award_type_codes"] == ["07"] and cfg["time_period_days"] == 90 and cfg["limit"] == 5


def test_fetch_awards_uses_config(monkeypatch):
    f = _load()
    captured = {}

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"results": [{"Award ID": "x", "Recipient Name": "y", "Award Amount": 1}]}).encode()

    def fake_urlopen(req, timeout=25):
        captured["body"] = json.loads(req.data.decode())
        return FakeResp()
    monkeypatch.setattr(f.urllib.request, "urlopen", fake_urlopen)
    f._fetch_awards({"award_type_codes": ["06", "10"], "time_period_days": 30, "limit": 7, "page": 3})
    assert captured["body"]["filters"]["award_type_codes"] == ["06", "10"]
    assert captured["body"]["limit"] == 7 and captured["body"]["page"] == 3


# --- v3.6.0: full builder (agencies, locations, sub-awards, date type/range) ---

def test_to_payment_prime_and_sub():
    f = _load()
    prime = f._to_payment({"Recipient Name": "LOCKHEED MARTIN CORP", "Award ID": "P1", "Award Amount": 100})
    assert prime == {"payment_id": "USASPEND-P1", "payee": "LOCKHEED MARTIN CORP", "amount": 100.0}
    sub = f._to_payment({"Sub-Awardee Name": "AVNET INC", "Sub-Award ID": "S1", "Sub-Award Amount": 55000}, subawards=True)
    assert sub == {"payment_id": "USASPEND-SUB-S1", "payee": "AVNET INC", "amount": 55000.0}
    # prime fields on a subaward map (and vice versa) -> dropped, no crash
    assert f._to_payment({"Recipient Name": "X", "Award ID": "P"}, subawards=True) is None


def _capture_body(f, monkeypatch):
    captured = {}

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps({"results": [{"Award ID": "x", "Recipient Name": "y", "Award Amount": 1}]}).encode()
    monkeypatch.setattr(f.urllib.request, "urlopen",
                        lambda req, timeout=25: captured.__setitem__("body", json.loads(req.data.decode())) or FakeResp())
    return captured


def test_fetch_awards_full_filters_and_subawards(monkeypatch):
    f = _load()
    captured = _capture_body(f, monkeypatch)
    f._fetch_awards({
        "award_type_codes": ["A", "B", "C", "D"], "subawards": True, "limit": 10,
        "date_type": "last_modified_date", "start_date": "2026-01-01", "end_date": "2026-07-07",
        "agencies": [{"type": "awarding", "tier": "toptier", "name": "Department of Veterans Affairs"}],
        "recipient_locations": [{"country": "USA", "state": "VA"}],
    })
    b = captured["body"]
    assert b["subawards"] is True
    assert b["fields"] == ["Sub-Award ID", "Sub-Awardee Name", "Sub-Award Amount"]
    assert b["sort"] == "Sub-Award Amount"
    assert b["filters"]["agencies"][0]["name"] == "Department of Veterans Affairs"
    assert b["filters"]["recipient_locations"] == [{"country": "USA", "state": "VA"}]
    tp = b["filters"]["time_period"][0]
    assert tp == {"start_date": "2026-01-01", "end_date": "2026-07-07", "date_type": "last_modified_date"}


def test_fetch_awards_prime_defaults_no_extra_filters(monkeypatch):
    f = _load()
    captured = _capture_body(f, monkeypatch)
    f._fetch_awards({"award_type_codes": ["A"], "time_period_days": 365, "limit": 5})
    b = captured["body"]
    assert b["subawards"] is False and b["fields"][0] == "Award ID"
    assert "agencies" not in b["filters"] and "recipient_locations" not in b["filters"]


# --- v3.8.3: Run-now uses page 1; a narrow filter falls back off an empty rotating page ---

def test_on_demand_run_now_uses_page_1(monkeypatch):
    """An inline Run-now config fetches page 1 (top results of the admin's exact filter),
    not the hourly rotating page that would overshoot a narrow filter."""
    f = _load()
    cfg = f._load_config({"feeder_config": {"award_type_codes": ["A"], "limit": 100}})
    assert cfg["page"] == 1
    captured = _capture_body(f, monkeypatch)
    f._fetch_awards(cfg)
    assert captured["body"]["page"] == 1


def test_fetch_awards_falls_back_to_page_1_when_rotating_page_is_empty(monkeypatch):
    """A scheduled/narrow query whose rotating page overshoots the result set retries
    page 1 instead of reporting nothing."""
    f = _load()
    monkeypatch.setattr(f, "_page_for_now", lambda: 424)  # force a high rotating page
    pages = []

    class FakeResp:
        def __init__(self, body): self._body = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self._body

    def fake_urlopen(req, timeout=25):
        page = json.loads(req.data.decode())["page"]
        pages.append(page)
        results = [] if page != 1 else [{"Award ID": "A1", "Recipient Name": "ACME", "Award Amount": 9}]
        return FakeResp(json.dumps({"results": results}).encode())

    monkeypatch.setattr(f.urllib.request, "urlopen", fake_urlopen)
    out = f._fetch_awards({"award_type_codes": ["A"], "time_period_days": 365, "limit": 100})
    assert pages == [424, 1]                    # tried the rotating page, then fell back to page 1
    assert out and out[0]["Recipient Name"] == "ACME"
