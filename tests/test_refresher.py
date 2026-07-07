"""Component G - Scheduled Reference Refresher tests (v3.4.0).

Deterministic: moto for S3, monkeypatched SAM fetch + Titan embed. Pins the SAM row
normalization, the skip-if-unchanged guard, the versioned republish, and graceful
fetch-error handling, with no network and no Bedrock.
"""
import importlib.util
import json
from pathlib import Path

import boto3
from moto import mock_aws

ROOT = Path(__file__).resolve().parent.parent
REGION = "us-east-2"
BUCKET = "treasury-dev-reference-test"


def _load():
    path = ROOT / "src" / "component_g_refresher" / "app.py"
    spec = importlib.util.spec_from_file_location("component_g_refresher_app", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _row(name, schema="LegalEntity", ident="U1", sanctions="Reciprocal - Active - 2025"):
    return {"name": name, "schema": schema, "identifiers": ident, "sanctions": sanctions}


def test_normalize_row_active_and_inactive():
    g = _load()
    e = g._normalize_row(_row("YATAI SMART INDUSTRIAL NEW CITY", ident="GQBPAV1TFF41"))
    assert e["name"] == "YATAI SMART INDUSTRIAL NEW CITY" and e["source"] == "sam_exclusions"
    assert e["severity"] == "high" and e["classification"] == "Entity" and e["uei"] == "GQBPAV1TFF41"
    # "Inactive" must not match the substring "active"
    assert g._normalize_row(_row("Old Co", sanctions="Reciprocal - Inactive - 2000")) is None
    assert g._normalize_row(_row("", sanctions="P - Active - d")) is None
    assert g._normalize_row(_row("Jane Doe", schema="Person"))["classification"] == "Individual"


def test_normalize_all_dedupes():
    g = _load()
    out = g._normalize_all([_row("Dup", ident="U1"), _row("dup", ident="U1"), _row("Other", ident="U2")])
    assert len(out) == 2


def _seed_current(s3, version=4):
    doc = {
        "version": version, "semantic_threshold": 0.72,
        "sources": {"oig_leie": "synthetic", "sam_exclusions": "old"},
        "entries": [
            {"name": "Globex Offshore Inc", "tin": "900000004", "source": "oig_leie",
             "severity": "high", "embedding": [0.1, 0.2]},
            {"name": "Old SAM Co", "tin": "", "uei": "OLD1", "source": "sam_exclusions",
             "severity": "high", "embedding": [0.3, 0.4]},
        ],
    }
    s3.put_object(Bucket=BUCKET, Key="reference/current.json", Body=json.dumps(doc).encode())


def test_handler_publishes_when_changed(monkeypatch):
    g = _load()
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
        _seed_current(s3, version=4)
        monkeypatch.setenv("REFERENCE_BUCKET", BUCKET)
        monkeypatch.setattr(g, "_fetch_sam", lambda limit: [_row("New SAM Vendor", ident="NEW9")])
        monkeypatch.setattr(g, "_embed", lambda text: [9.9, 9.9])
        out = g.handler({})
        assert out["refreshed"] is True and out["version"] == 5
        cur = json.loads(s3.get_object(Bucket=BUCKET, Key="reference/current.json")["Body"].read())
        names = {e["name"] for e in cur["entries"]}
        assert "New SAM Vendor" in names            # new real SAM entry embedded + added
        assert "Old SAM Co" not in names            # stale synthetic-SAM entry replaced
        assert "Globex Offshore Inc" in names       # non-SAM synthetic carried verbatim
        glob = next(e for e in cur["entries"] if e["name"] == "Globex Offshore Inc")
        assert glob["embedding"] == [0.1, 0.2]      # kept its original embedding (not re-embedded)


def test_handler_skips_when_unchanged(monkeypatch):
    g = _load()
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
        _seed_current(s3, version=4)
        monkeypatch.setenv("REFERENCE_BUCKET", BUCKET)
        # same key as the current SAM entry ("Old SAM Co" / OLD1) -> no republish
        monkeypatch.setattr(g, "_fetch_sam", lambda limit: [_row("Old SAM Co", ident="OLD1")])
        embed_calls = []
        monkeypatch.setattr(g, "_embed", lambda text: embed_calls.append(text) or [0, 0])
        out = g.handler({})
        assert out["refreshed"] is False and out["reason"] == "unchanged" and out["version"] == 4
        assert embed_calls == []  # unchanged -> no embedding cost


def test_handler_fetch_error_keeps_version(monkeypatch):
    g = _load()
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION})
        _seed_current(s3, version=4)
        monkeypatch.setenv("REFERENCE_BUCKET", BUCKET)

        def boom(limit):
            raise RuntimeError("opensanctions down")
        monkeypatch.setattr(g, "_fetch_sam", boom)
        out = g.handler({})
        assert out["refreshed"] is False and out["reason"] == "fetch_error" and out["version"] == 4
