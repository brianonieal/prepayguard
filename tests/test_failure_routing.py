"""Commitment 2 evidence — routing to manual review (ambiguous) and DLQ (failure)."""
import json


def _sqs_event(*payments):
    return {"Records": [{"messageId": f"m{i}", "body": json.dumps(p)} for i, p in enumerate(payments)]}


def _scored(payment_id, disposition, score=0):
    return {
        "payment_id": payment_id, "payee": "Vendor", "amount": 100.0,
        "enrichment": {"matches": [], "match_count": 0, "highest_confidence": 0},
        "risk": {"disposition": disposition, "score": score, "reasons": ["test"]},
    }


def _review_depth(sqs, url):
    return len(sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10).get("Messages", []))


def test_review_disposition_is_routed_to_human_queue(disposition, monkeypatch):
    app = disposition["load"]("component_d_disposition")
    monkeypatch.setattr(app.urlrequest, "urlopen", lambda *a, **k: None)  # stub webhook
    app.handler(_sqs_event(_scored("p1", "review", score=60)))
    assert _review_depth(disposition["sqs"], disposition["review_url"]) == 1


def test_approved_payment_is_not_routed(disposition):
    app = disposition["load"]("component_d_disposition")
    app.handler(_sqs_event(_scored("p2", "approve")))
    # Audit still written, but nothing sent to review.
    assert _review_depth(disposition["sqs"], disposition["review_url"]) == 0


def test_rejected_payment_is_audited_not_routed(disposition):
    app = disposition["load"]("component_d_disposition")
    app.handler(_sqs_event(_scored("p3", "reject", score=95)))
    assert _review_depth(disposition["sqs"], disposition["review_url"]) == 0
    assert len(disposition["s3"].list_objects_v2(Bucket=disposition["bucket"]).get("Contents", [])) == 1


def test_processing_failure_is_reported_for_redrive(disposition):
    # A malformed record fails -> reported in batchItemFailures so SQS re-drives
    # it and (after maxReceiveCount) routes it to the DLQ (commitment 2).
    app = disposition["load"]("component_d_disposition")
    result = app.handler({"Records": [
        {"messageId": "ok", "body": json.dumps(_scored("p4", "approve"))},
        {"messageId": "bad", "body": "{ not json"},
    ]})
    assert [f["itemIdentifier"] for f in result["batchItemFailures"]] == ["bad"]
