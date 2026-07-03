"""Component B — reference-match enrichment (DEC-14)."""
import json


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


def test_partial_batch_failure_isolates_bad_record(worker):
    app = worker["load"]("component_b_enrichment")
    result = app.handler({"Records": [
        {"messageId": "ok", "body": json.dumps({"payment_id": "p4", "amount": 1, "payee": "Fine Vendor"})},
        {"messageId": "bad", "body": "{ not json"},
    ]})
    assert [f["itemIdentifier"] for f in result["batchItemFailures"]] == ["bad"]
    # The good record still made it through.
    assert len(_drain(worker["sqs"], worker["out_url"])) == 1
