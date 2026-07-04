"""Component E — batch ingest: S3-triggered bulk intake sharing Component A's
idempotency store + intake queue (DEC-16). moto-backed S3/DynamoDB/SQS."""
import json

import boto3

REGION = "us-east-2"
CSV = "payment_id,payee,payee_tin,amount\nP-1,Acme,900000001,100\nP-2,Beta,,50\n"


def _event(env, key, text):
    env["s3"].put_object(Bucket=env["bucket"], Key=key, Body=text.encode())
    return {"Records": [{"s3": {"bucket": {"name": env["bucket"]}, "object": {"key": key}}}]}


def _drain(env):
    """Receive+delete every queued message; return the decoded payment bodies."""
    bodies = []
    while True:
        got = env["sqs"].receive_message(QueueUrl=env["queue_url"], MaxNumberOfMessages=10).get("Messages", [])
        if not got:
            return bodies
        for m in got:
            bodies.append(json.loads(m["Body"]))
            env["sqs"].delete_message(QueueUrl=env["queue_url"], ReceiptHandle=m["ReceiptHandle"])


def _summary(env, batch_id):
    return boto3.resource("dynamodb", region_name=REGION).Table(env["batches_table"]).get_item(
        Key={"batch_id": batch_id})["Item"]


def test_valid_csv_enqueues_each_row_and_summarizes(batch_ingest):
    out = batch_ingest["app"].handler(_event(batch_ingest, "batch-imports/b-1/payroll.csv", CSV))
    summ = out["batches"][0]
    assert summ["batch_id"] == "b-1"
    assert summ["queued"] == 2 and summ["duplicate"] == 0 and summ["rejected"] == 0 and summ["total"] == 2
    bodies = _drain(batch_ingest)
    assert {b["payment_id"] for b in bodies} == {"P-1", "P-2"}
    # summary persisted to the batches table for the console to poll
    assert _summary(batch_ingest, "b-1")["queued"] == 2


def test_malformed_rows_are_rejected_not_enqueued(batch_ingest):
    csv = "payment_id,payee,amount\nP-1,Acme,100\n,NoId,5\nP-3,Gamma,notanumber\n"
    summ = batch_ingest["app"].handler(_event(batch_ingest, "batch-imports/b-2/f.csv", csv))["batches"][0]
    assert summ["queued"] == 1 and summ["rejected"] == 2 and len(summ["errors"]) == 2
    assert {b["payment_id"] for b in _drain(batch_ingest)} == {"P-1"}


def test_duplicate_across_paths_not_reenqueued(batch_ingest):
    # Component A already SENT P-1 via the single API (same shared table) — E must
    # treat it as a duplicate and only enqueue the genuinely new P-2 (DEC-16).
    boto3.resource("dynamodb", region_name=REGION).Table(batch_ingest["table"]).put_item(
        Item={"payment_id": "P-1", "status": "SENT", "message_id": "prior", "received_at": 1})
    summ = batch_ingest["app"].handler(_event(batch_ingest, "batch-imports/b-3/f.csv", CSV))["batches"][0]
    assert summ["duplicate"] == 1 and summ["queued"] == 1
    assert {b["payment_id"] for b in _drain(batch_ingest)} == {"P-2"}


def test_reprocessing_same_file_is_idempotent(batch_ingest):
    ev = _event(batch_ingest, "batch-imports/b-4/f.csv", CSV)
    first = batch_ingest["app"].handler(ev)["batches"][0]
    assert first["queued"] == 2
    # S3 re-delivers the same object: every row is now SENT → all duplicates, no new sends.
    second = batch_ingest["app"].handler(ev)["batches"][0]
    assert second["queued"] == 0 and second["duplicate"] == 2
    assert len(_drain(batch_ingest)) == 2  # still only the original two messages


def test_intra_file_duplicate_deduped(batch_ingest):
    # Same payment_id twice in ONE file → enqueued once, the repeat counted duplicate.
    csv = "payment_id,payee,amount\nDUP-1,Acme,10\nDUP-1,Acme,10\nUNIQ-2,Beta,20\n"
    summ = batch_ingest["app"].handler(_event(batch_ingest, "batch-imports/b-6/f.csv", csv))["batches"][0]
    assert summ["queued"] == 2 and summ["duplicate"] == 1
    assert sorted(b["payment_id"] for b in _drain(batch_ingest)) == ["DUP-1", "UNIQ-2"]


def test_empty_file_summarized_not_crashed(batch_ingest):
    summ = batch_ingest["app"].handler(_event(batch_ingest, "batch-imports/b-5/empty.csv", ""))["batches"][0]
    assert summ["queued"] == 0 and summ["rejected"] == 1  # "file is empty"
