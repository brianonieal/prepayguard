"""Commitment 4 evidence — immutable audit log via S3 Object Lock (DEC-4).

The gold-standard immutability proof is the LIVE test (scripts/live_object_lock_proof.py)
run against a real Compliance-mode bucket. These moto-backed tests prove the
handler writes a well-formed, retention-locked, integrity-hashed audit record.
"""
import hashlib
import json

import pytest
from botocore.exceptions import ClientError


def _sqs_event(*payments):
    return {"Records": [{"messageId": f"m{i}", "body": json.dumps(p)} for i, p in enumerate(payments)]}


def _scored(payment_id, disposition, score=0, matches=None):
    return {
        "payment_id": payment_id, "payee": "Vendor", "amount": 100.0,
        "enrichment": {"matches": matches or [], "match_count": len(matches or []), "highest_confidence": 0},
        "risk": {"disposition": disposition, "score": score, "reasons": ["test"]},
    }


def _only_object(s3, bucket):
    objs = s3.list_objects_v2(Bucket=bucket).get("Contents", [])
    assert len(objs) == 1
    return objs[0]["Key"]


def test_audit_record_is_written(disposition):
    app = disposition["load"]("component_d_disposition")
    app.handler(_sqs_event(_scored("p1", "approve")))
    key = _only_object(disposition["s3"], disposition["bucket"])
    assert key.startswith("audit/")
    assert "p1" in key


def test_bucket_enforces_compliance_object_lock(disposition):
    # Config proof (deterministic in moto): the audit bucket the handler writes
    # to is Object-Lock COMPLIANCE. Per-object retention auto-applies in real S3
    # (moto does not emulate that read path); actual enforcement is proven by
    # scripts/live_object_lock_proof.py against a real bucket.
    app = disposition["load"]("component_d_disposition")
    app.handler(_sqs_event(_scored("p2", "reject", score=95)))
    s3, bucket = disposition["s3"], disposition["bucket"]
    _only_object(s3, bucket)  # an audit object was written
    cfg = s3.get_object_lock_configuration(Bucket=bucket)["ObjectLockConfiguration"]
    assert cfg["ObjectLockEnabled"] == "Enabled"
    assert cfg["Rule"]["DefaultRetention"]["Mode"] == "COMPLIANCE"


def test_audit_integrity_hash_verifies(disposition):
    app = disposition["load"]("component_d_disposition")
    app.handler(_sqs_event(_scored("p3", "review", score=60)))
    s3, bucket = disposition["s3"], disposition["bucket"]
    key = _only_object(s3, bucket)
    record = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    stored = record.pop("integrity")
    recomputed = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert stored["sha256"] == recomputed  # content is exactly what was decided


def test_locked_audit_object_cannot_be_deleted(disposition):
    # moto enforces Object Lock retention: deleting the version is refused.
    app = disposition["load"]("component_d_disposition")
    app.handler(_sqs_event(_scored("p4", "reject", score=95)))
    s3, bucket = disposition["s3"], disposition["bucket"]
    key = _only_object(s3, bucket)
    version = s3.list_object_versions(Bucket=bucket, Prefix=key)["Versions"][0]["VersionId"]
    with pytest.raises(ClientError) as ei:
        s3.delete_object(Bucket=bucket, Key=key, VersionId=version)
    assert ei.value.response["Error"]["Code"] in ("AccessDenied", "InvalidRequest")
