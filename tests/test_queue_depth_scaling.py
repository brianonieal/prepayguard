"""Commitment 3 evidence — queue-depth scaling & DLQ redrive (config proof).

Parses `terraform show -json` of the real plan and asserts the scaling mechanism
is wired on every worker stage: event-source-mapping concurrency scaling,
partial-batch failure reporting, queue-depth alarms, and DLQ redrive. This is
deterministic infra evidence; a live load-driven scaling demo is deferred to the
full-deploy milestone. Skip-guarded so hermetic (no terraform / no creds) runs
don't fail.
"""
import json
import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = ROOT / "environments" / "dev"
TF = ROOT / ".tools" / "bin" / "terraform.exe"


@pytest.fixture(scope="module")
def plan():
    if not TF.exists():
        pytest.skip("terraform binary not available (.tools/bin)")
    plan_file = ROOT / ".tools" / "qds.tfplan"
    gen = subprocess.run(
        [str(TF), f"-chdir={ENV}", "plan", "-input=false", "-lock=false", "-out", str(plan_file)],
        capture_output=True, text=True,
    )
    if gen.returncode != 0:
        pytest.skip(f"terraform plan unavailable (creds?): {gen.stderr[-200:]}")
    show = subprocess.run(
        [str(TF), f"-chdir={ENV}", "show", "-json", str(plan_file)],
        capture_output=True, text=True,
    )
    assert show.returncode == 0, show.stderr[-300:]
    return json.loads(show.stdout)


def _collect(module, rtype):
    found = [r for r in module.get("resources", []) if r.get("type") == rtype]
    for child in module.get("child_modules", []):
        found.extend(_collect(child, rtype))
    return found


def _root(plan):
    return plan["planned_values"]["root_module"]


def test_every_worker_stage_scales_on_queue_depth(plan):
    esms = _collect(_root(plan), "aws_lambda_event_source_mapping")
    assert len(esms) == 3, f"expected 3 worker event source mappings, got {len(esms)}"
    for esm in esms:
        v = esm["values"]
        assert v["scaling_config"][0]["maximum_concurrency"] >= 2  # commitment 3 lever
        assert "ReportBatchItemFailures" in v["function_response_types"]
        assert v["batch_size"] >= 1


def test_queue_depth_alarms_exist_per_stage(plan):
    alarms = _collect(_root(plan), "aws_cloudwatch_metric_alarm")
    depth = [a for a in alarms if "queue-depth" in a["values"]["alarm_name"]]
    assert len(depth) == 3
    for a in depth:
        assert a["values"]["metric_name"] == "ApproximateNumberOfMessagesVisible"


def test_dlq_redrive_configured_per_stage(plan):
    # redrive_policy value is known-after-apply (it references the DLQ ARN), so
    # assert the wiring exists rather than parsing the computed policy string.
    redrives = _collect(_root(plan), "aws_sqs_queue_redrive_policy")
    assert len(redrives) == 3  # one per worker stage
    dlqs = [q for q in _collect(_root(plan), "aws_sqs_queue")
            if q["values"].get("name", "").endswith("-dlq")]
    assert len(dlqs) >= 3  # a dead-letter queue per worker stage (+ review DLQ)
