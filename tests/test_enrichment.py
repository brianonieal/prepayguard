"""Component B — reference-match enrichment (DEC-14) + versioned store (v2.1.0)."""
import json

import boto3

REGION = "us-east-2"


def _sqs_event(*payments):
    return {"Records": [{"messageId": f"m{i}", "body": json.dumps(p)} for i, p in enumerate(payments)]}


def _drain(sqs, url):
    msgs = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10).get("Messages", [])
    return [json.loads(m["Body"]) for m in msgs]


def test_clean_payment_has_no_matches(worker):
    app = worker["load"]("component_b_enrichment")
    app.handler(_sqs_event({"payment_id": "p1", "amount": 10, "payee": "Totally Legit Vendor"}))
    out = _drain(worker["sqs"], worker["out_url"])
    assert len(out) == 1
    assert out[0]["enrichment"]["match_count"] == 0


def test_tin_match_is_flagged(worker):
    app = worker["load"]("component_b_enrichment")
    # 900000001 is the synthetic death_master_file entry.
    app.handler(_sqs_event({"payment_id": "p2", "amount": 10, "payee": "Some Other Name", "payee_tin": "900000001"}))
    out = _drain(worker["sqs"], worker["out_url"])[0]
    assert out["enrichment"]["match_count"] >= 1
    m = out["enrichment"]["matches"][0]
    assert m["matched_on"] == "tin"
    assert m["source"] == "death_master_file"
    assert m["confidence"] == 95


def test_name_match_survives_normalization(worker):
    app = worker["load"]("component_b_enrichment")
    # "acme  SHELL, llc" normalizes to the same key as "Acme Shell LLC".
    app.handler(_sqs_event({"payment_id": "p3", "amount": 10, "payee": "acme  SHELL, llc"}))
    out = _drain(worker["sqs"], worker["out_url"])[0]
    assert out["enrichment"]["match_count"] >= 1
    assert out["enrichment"]["matches"][0]["matched_on"] in ("name_exact", "name_fuzzy")


# --- v2.1.0: versioned reference store ---

def _seed_store(monkeypatch, doc, bucket="treasury-dev-reference-test"):
    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
    s3.put_object(Bucket=bucket, Key="reference/current.json", Body=json.dumps(doc).encode())
    monkeypatch.setenv("REFERENCE_BUCKET", bucket)


def test_screening_cites_store_version(worker, monkeypatch):
    # B fetches the ACTIVE list from the store and stamps its version on the
    # enrichment block — the citation D carries into the audit record.
    _seed_store(monkeypatch, {
        "version": 7,
        "entries": [{"name": "Newly Listed Corp", "tin": "900000099",
                     "source": "sam_exclusions", "severity": "high"}],
    })
    app = worker["load"]("component_b_enrichment")
    app.handler(_sqs_event({"payment_id": "p5", "amount": 10, "payee": "Newly Listed Corp"}))
    out = _drain(worker["sqs"], worker["out_url"])[0]
    assert out["enrichment"]["reference_version"] == 7
    assert out["enrichment"]["match_count"] >= 1  # matched from STORE content, not the bundle


def test_bundled_fallback_reports_version_zero(worker):
    # No store configured (tests/local): bundled seed, cited as version 0.
    app = worker["load"]("component_b_enrichment")
    app.handler(_sqs_event({"payment_id": "p6", "amount": 10, "payee": "Clean Vendor"}))
    assert _drain(worker["sqs"], worker["out_url"])[0]["enrichment"]["reference_version"] == 0


def test_store_failure_with_no_cache_fails_the_message(worker, monkeypatch):
    # Never screen blind: store configured but unreadable + no warm cache ->
    # the message fails the batch (retry/DLQ path, commitment 2).
    monkeypatch.setenv("REFERENCE_BUCKET", "does-not-exist-treasury-ref")
    app = worker["load"]("component_b_enrichment")
    result = app.handler(_sqs_event({"payment_id": "p7", "amount": 10, "payee": "Anyone"}))
    assert [f["itemIdentifier"] for f in result["batchItemFailures"]] == ["m0"]
    assert _drain(worker["sqs"], worker["out_url"]) == []


def test_partial_batch_failure_isolates_bad_record(worker):
    app = worker["load"]("component_b_enrichment")
    result = app.handler({"Records": [
        {"messageId": "ok", "body": json.dumps({"payment_id": "p4", "amount": 1, "payee": "Fine Vendor"})},
        {"messageId": "bad", "body": "{ not json"},
    ]})
    assert [f["itemIdentifier"] for f in result["batchItemFailures"]] == ["bad"]
    # The good record still made it through.
    assert len(_drain(worker["sqs"], worker["out_url"])) == 1
