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


# --- v2.2.0: semantic matching (Bedrock embeddings mocked for determinism) ---

def test_semantic_match_when_string_match_misses(worker, monkeypatch):
    _seed_store(monkeypatch, {
        "version": 5, "semantic_threshold": 0.8,
        "entries": [{"name": "Globex Offshore Inc", "tin": "900000004",
                     "source": "oig_leie", "severity": "high", "embedding": [1.0, 0.0, 0.0]}],
    })
    app = worker["load"]("component_b_enrichment")
    # payee string doesn't match "Globex Offshore Inc" at all; its embedding does.
    monkeypatch.setattr(app, "_embed", lambda text: [0.95, 0.31, 0.0])  # cosine ~0.95
    app.handler(_sqs_event({"payment_id": "s1", "amount": 10, "payee": "Overseas Holdings Group"}))
    m = _drain(worker["sqs"], worker["out_url"])[0]["enrichment"]["matches"]
    assert len(m) == 1 and m[0]["matched_on"] == "name_semantic"
    assert m[0]["source"] == "oig_leie" and m[0]["similarity"] >= 0.8


def test_semantic_below_threshold_no_match(worker, monkeypatch):
    _seed_store(monkeypatch, {"version": 5, "semantic_threshold": 0.9,
                              "entries": [{"name": "Globex", "tin": "", "source": "oig_leie",
                                           "severity": "high", "embedding": [1.0, 0.0, 0.0]}]})
    app = worker["load"]("component_b_enrichment")
    monkeypatch.setattr(app, "_embed", lambda text: [0.5, 0.87, 0.0])  # cosine ~0.5 < 0.9
    app.handler(_sqs_event({"payment_id": "s2", "amount": 10, "payee": "Totally Different Vendor"}))
    assert _drain(worker["sqs"], worker["out_url"])[0]["enrichment"]["match_count"] == 0


def test_semantic_skipped_when_string_matches(worker, monkeypatch):
    _seed_store(monkeypatch, {"version": 5, "entries": [{"name": "Acme Shell LLC", "tin": "900000002",
                              "source": "sam_exclusions", "severity": "high", "embedding": [1.0, 0.0, 0.0]}]})
    app = worker["load"]("component_b_enrichment")
    called = []
    monkeypatch.setattr(app, "_embed", lambda text: called.append(text) or [1.0, 0.0, 0.0])
    app.handler(_sqs_event({"payment_id": "s3", "amount": 10, "payee": "Acme Shell LLC"}))  # exact
    out = _drain(worker["sqs"], worker["out_url"])[0]
    assert out["enrichment"]["matches"][0]["matched_on"] == "name_exact"
    assert called == []  # embed (Bedrock) never runs when a string rule already matched


def test_semantic_bedrock_error_degrades_not_dlq(worker, monkeypatch):
    _seed_store(monkeypatch, {"version": 5, "entries": [{"name": "Globex", "tin": "", "source": "oig_leie",
                              "severity": "high", "embedding": [1.0, 0.0, 0.0]}]})
    app = worker["load"]("component_b_enrichment")

    def boom(text):
        raise RuntimeError("bedrock unavailable")
    monkeypatch.setattr(app, "_embed", boom)
    result = app.handler(_sqs_event({"payment_id": "s4", "amount": 10, "payee": "Unmatched Vendor"}))
    assert result["batchItemFailures"] == []  # screened without semantic, not DLQ'd
    assert _drain(worker["sqs"], worker["out_url"])[0]["enrichment"]["match_count"] == 0


def test_partial_batch_failure_isolates_bad_record(worker):
    app = worker["load"]("component_b_enrichment")
    result = app.handler({"Records": [
        {"messageId": "ok", "body": json.dumps({"payment_id": "p4", "amount": 1, "payee": "Fine Vendor"})},
        {"messageId": "bad", "body": "{ not json"},
    ]})
    assert [f["itemIdentifier"] for f in result["batchItemFailures"]] == ["bad"]
    # The good record still made it through.
    assert len(_drain(worker["sqs"], worker["out_url"])) == 1
