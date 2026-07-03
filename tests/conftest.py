"""Shared pytest fixtures for Component A: moto-backed DynamoDB + SQS.

Component A's handler (src/component_a_intake/app.py) lazily caches its boto3
clients at module scope for warm-container reuse. The `aws` fixture resets those
caches so each test binds to a fresh moto mock.
"""
import boto3
import pytest
from moto import mock_aws

REGION = "us-east-2"
TABLE = "treasury-dev-intake-idempotency"
QUEUE = "treasury-dev-intake-out"


@pytest.fixture(autouse=True)
def _aws_credentials(monkeypatch):
    # Never touch real AWS: dummy creds + region for every test.
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("IDEMPOTENCY_TABLE", TABLE)
    monkeypatch.setenv("IDEMPOTENCY_TTL_DAYS", "7")


@pytest.fixture
def aws(monkeypatch):
    with mock_aws():
        ddb = boto3.client("dynamodb", region_name=REGION)
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "payment_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "payment_id", "AttributeType": "S"}],
            BillingMode="PROVISIONED",
            ProvisionedThroughput={"ReadCapacityUnits": 25, "WriteCapacityUnits": 25},
        )
        ddb.get_waiter("table_exists").wait(TableName=TABLE)

        sqs = boto3.client("sqs", region_name=REGION)
        queue_url = sqs.create_queue(QueueName=QUEUE)["QueueUrl"]
        monkeypatch.setenv("OUTPUT_QUEUE_URL", queue_url)

        import app
        app._dynamodb = None  # reset lazily-cached clients so they bind to this mock
        app._sqs = None

        yield {"app": app, "ddb": ddb, "sqs": sqs, "queue_url": queue_url, "table": TABLE}
