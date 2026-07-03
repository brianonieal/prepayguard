"""Commitment 1 evidence — payment-ID idempotency (DEC-13).

Atomicity note: DynamoDB's conditional PutItem is evaluated server-side and is
strongly consistent, so under concurrent identical payment_ids exactly one write
wins. That guarantee is asserted deterministically here via
`test_conditional_write_refuses_duplicate` (moto honors ConditionExpression);
live-concurrency verification is deferred to the first live-AWS gate.
"""
import json

import pytest
from botocore.exceptions import ClientError


def _event(payment_id, amount=100.0, payee="ACME Corp"):
    return {"body": json.dumps({"payment_id": payment_id, "amount": amount, "payee": payee})}


def _queue_depth(sqs, queue_url):
    attrs = sqs.get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=["ApproximateNumberOfMessages"]
    )
    return int(attrs["Attributes"]["ApproximateNumberOfMessages"])


def test_first_seen_payment_is_queued(aws):
    resp = aws["app"].handler(_event("pay-1"))
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert body["status"] == "queued"
    assert body["idempotent_replay"] is False
    assert body["message_id"]
    assert _queue_depth(aws["sqs"], aws["queue_url"]) == 1


def test_duplicate_replays_original_result(aws):
    # The core of commitment 1: replay returns the ORIGINAL result, not an error,
    # and does NOT enqueue a second time.
    app = aws["app"]
    first = json.loads(app.handler(_event("pay-2"))["body"])
    resp = app.handler(_event("pay-2"))
    second = json.loads(resp["body"])
    assert resp["statusCode"] == 200
    assert second["idempotent_replay"] is True
    assert second["message_id"] == first["message_id"]
    assert _queue_depth(aws["sqs"], aws["queue_url"]) == 1


def test_distinct_payments_both_queued(aws):
    app = aws["app"]
    app.handler(_event("pay-3"))
    app.handler(_event("pay-4"))
    assert _queue_depth(aws["sqs"], aws["queue_url"]) == 2


def test_conditional_write_refuses_duplicate(aws):
    # The atomic guard itself: once a payment_id exists, a second
    # attribute_not_exists PutItem is refused server-side. This is what makes the
    # mechanism correct under concurrent duplicate deliveries.
    app = aws["app"]
    app.handler(_event("pay-5"))
    with pytest.raises(ClientError) as ei:
        app._table().put_item(
            Item={"payment_id": "pay-5", "status": "PENDING"},
            ConditionExpression="attribute_not_exists(payment_id)",
        )
    assert ei.value.response["Error"]["Code"] == "ConditionalCheckFailedException"


def test_crash_before_enqueue_is_recovered(aws, monkeypatch):
    # Objection 2 (the silent-loss window): the Lambda dies after the PENDING
    # write but before the SQS send. A retry must re-drive the send — not swallow
    # the payment, and not enqueue it twice.
    app = aws["app"]
    client = app._sqs_client()
    real_send = client.send_message
    calls = {"n": 0}

    def flaky_send(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated crash before enqueue")
        return real_send(**kwargs)

    monkeypatch.setattr(client, "send_message", flaky_send)

    with pytest.raises(RuntimeError):
        app.handler(_event("pay-6"))  # PENDING written, then "crash"

    resp = json.loads(app.handler(_event("pay-6"))["body"])  # retry re-drives
    assert resp["status"] == "queued"
    assert resp["idempotent_replay"] is False  # re-drive from PENDING, not a SENT replay
    assert _queue_depth(aws["sqs"], aws["queue_url"]) == 1  # exactly one, no loss, no dup


def test_missing_payment_id_is_rejected(aws):
    resp = aws["app"].handler({"body": json.dumps({"amount": 5})})
    assert resp["statusCode"] == 400
    assert _queue_depth(aws["sqs"], aws["queue_url"]) == 0
