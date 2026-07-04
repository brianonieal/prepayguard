"""DEC-7 evidence — review-notification webhook + scoped Secrets Manager retrieval."""
import json


def _sqs_event(*payments):
    return {"Records": [{"messageId": f"m{i}", "body": json.dumps(p)} for i, p in enumerate(payments)]}


def _scored(payment_id, disposition, score=0):
    return {
        "payment_id": payment_id, "payee": "Vendor", "amount": 100.0,
        "enrichment": {"matches": [], "match_count": 0, "highest_confidence": 0},
        "risk": {"disposition": disposition, "score": score, "reasons": ["test"]},
    }


class _WebhookSpy:
    def __init__(self):
        self.calls = []

    def __call__(self, req, timeout=None):
        self.calls.append({"url": req.full_url, "body": json.loads(req.data.decode()), "method": req.method})
        return None


def test_webhook_posted_with_secret_url_on_review(disposition, monkeypatch):
    app = disposition["load"]("component_d_disposition")
    spy = _WebhookSpy()
    monkeypatch.setattr(app.urlrequest, "urlopen", spy)

    app.handler(_sqs_event(_scored("p1", "review", score=60)))

    assert len(spy.calls) == 1
    # URL came from Secrets Manager (matches the secret the fixture stored).
    assert spy.calls[0]["url"] == "https://hooks.example.test/T000/B000/xyz"
    assert spy.calls[0]["method"] == "POST"
    assert spy.calls[0]["body"]["payment_id"] == "p1"


def test_audit_record_cites_reference_list_version(disposition, monkeypatch):
    # v2.1.0: the list version B screened against lands in the immutable audit
    # record's provenance — "what list said so?" stays answerable forever.
    app = disposition["load"]("component_d_disposition")
    monkeypatch.setattr(app.urlrequest, "urlopen", _WebhookSpy())
    scored = _scored("p-ref", "approve")
    scored["enrichment"]["reference_version"] = 42
    app.handler(_sqs_event(scored))
    key = disposition["s3"].list_objects_v2(
        Bucket=disposition["bucket"], Prefix="audit/")["Contents"][0]["Key"]
    record = json.loads(disposition["s3"].get_object(
        Bucket=disposition["bucket"], Key=key)["Body"].read())
    assert record["provenance"]["reference_list_version"] == 42


def test_review_item_records_submitter_for_sod(disposition, monkeypatch):
    # v2.0.0: the submitter identity Component A stamped must reach the reviews
    # table so the console can enforce segregation of duties.
    import boto3
    app = disposition["load"]("component_d_disposition")
    monkeypatch.setattr(app.urlrequest, "urlopen", _WebhookSpy())
    app.handler(_sqs_event({**_scored("p-sod", "review", score=60), "submitted_by": "user-123"}))
    item = boto3.resource("dynamodb", region_name="us-east-2").Table(
        disposition["reviews_table"]).get_item(Key={"payment_id": "p-sod"})["Item"]
    assert item["submitted_by"] == "user-123"


def test_no_webhook_for_approved_payment(disposition, monkeypatch):
    app = disposition["load"]("component_d_disposition")
    spy = _WebhookSpy()
    monkeypatch.setattr(app.urlrequest, "urlopen", spy)
    app.handler(_sqs_event(_scored("p2", "approve")))
    assert spy.calls == []


def test_no_webhook_for_rejected_payment(disposition, monkeypatch):
    app = disposition["load"]("component_d_disposition")
    spy = _WebhookSpy()
    monkeypatch.setattr(app.urlrequest, "urlopen", spy)
    app.handler(_sqs_event(_scored("p3", "reject", score=95)))
    assert spy.calls == []


def test_secret_is_fetched_from_secrets_manager(disposition, monkeypatch):
    # Prove the URL is retrieved via GetSecretValue, not hardcoded: rotate the
    # secret value and confirm the webhook follows it.
    app = disposition["load"]("component_d_disposition")
    disposition["sm"].put_secret_value(
        SecretId=disposition["secret_arn"], SecretString="https://hooks.example.test/rotated"
    )
    spy = _WebhookSpy()
    monkeypatch.setattr(app.urlrequest, "urlopen", spy)
    app.handler(_sqs_event(_scored("p4", "review", score=60)))
    assert spy.calls[0]["url"] == "https://hooks.example.test/rotated"
