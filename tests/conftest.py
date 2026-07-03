"""Shared pytest fixtures. moto-backed AWS + a per-component handler loader.

The three components each ship an `app.py`; they can't all be `import app`, so
`_load` imports each by file path under a unique module name. Every load is a
fresh module, so module-cached boto3 clients never leak across tests.
"""
import importlib.util
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

REGION = "us-east-2"
TABLE = "treasury-dev-intake-idempotency"
INTAKE_QUEUE = "treasury-dev-intake-out"
WORKER_OUT_QUEUE = "treasury-dev-worker-out"

_SRC = Path(__file__).resolve().parent.parent / "src"


def _load(component_name):
    path = _SRC / component_name / "app.py"
    spec = importlib.util.spec_from_file_location(f"{component_name}_app", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _aws_credentials(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("IDEMPOTENCY_TABLE", TABLE)
    monkeypatch.setenv("IDEMPOTENCY_TTL_DAYS", "7")


@pytest.fixture
def aws(monkeypatch):
    """Component A: DynamoDB idempotency table + output SQS queue."""
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
        queue_url = sqs.create_queue(QueueName=INTAKE_QUEUE)["QueueUrl"]
        monkeypatch.setenv("OUTPUT_QUEUE_URL", queue_url)
        yield {"app": _load("component_a_intake"), "ddb": ddb, "sqs": sqs, "queue_url": queue_url, "table": TABLE}


@pytest.fixture
def worker(monkeypatch):
    """Components B/C: an output SQS queue + a loader for the worker under test."""
    with mock_aws():
        sqs = boto3.client("sqs", region_name=REGION)
        out_url = sqs.create_queue(QueueName=WORKER_OUT_QUEUE)["QueueUrl"]
        monkeypatch.setenv("OUTPUT_QUEUE_URL", out_url)
        yield {"load": _load, "sqs": sqs, "out_url": out_url}
