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


@pytest.fixture
def disposition(monkeypatch):
    """Component D: Object Lock S3 bucket + review SQS queue + webhook secret."""
    bucket = "treasury-dev-audit-test"
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": REGION},
            ObjectLockEnabledForBucket=True,
        )
        s3.put_object_lock_configuration(
            Bucket=bucket,
            ObjectLockConfiguration={
                "ObjectLockEnabled": "Enabled",
                "Rule": {"DefaultRetention": {"Mode": "COMPLIANCE", "Days": 1}},
            },
        )
        sqs = boto3.client("sqs", region_name=REGION)
        review_url = sqs.create_queue(QueueName="treasury-dev-review")["QueueUrl"]
        sm = boto3.client("secretsmanager", region_name=REGION)
        secret_arn = sm.create_secret(
            Name="treasury-dev/review-webhook-url",
            SecretString="https://hooks.example.test/T000/B000/xyz",
        )["ARN"]
        ddb = boto3.client("dynamodb", region_name=REGION)
        reviews_table = "treasury-dev-reviews"
        ddb.create_table(
            TableName=reviews_table,
            KeySchema=[{"AttributeName": "payment_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "payment_id", "AttributeType": "S"}],
            BillingMode="PROVISIONED",
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )

        monkeypatch.setenv("AUDIT_BUCKET_NAME", bucket)
        monkeypatch.setenv("REVIEW_QUEUE_URL", review_url)
        monkeypatch.setenv("WEBHOOK_SECRET_ARN", secret_arn)
        monkeypatch.setenv("REVIEWS_TABLE_NAME", reviews_table)

        yield {
            "load": _load, "s3": s3, "sqs": sqs, "sm": sm, "ddb": ddb,
            "bucket": bucket, "review_url": review_url, "secret_arn": secret_arn,
            "reviews_table": reviews_table,
        }
