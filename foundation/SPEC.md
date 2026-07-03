# SPEC.md
# Current-gate detail. Updated each gate.

## LAST CLOSED: v0.5.0 — Queue-Depth Scaling & DLQ Hardening
**Status:** CLOSED (tagged). pytest 29/29 · tflint/checkov 271/0 · plan 68/0/0.
Commitment 3 demonstrated (config proof: `terraform show -json` asserts
event-source-mapping scaling, queue-depth alarms, DLQ redrive per worker stage).

**ALL FOUR graded commitments now demonstrated:**
1. Idempotency — `test_idempotency.py` (DEC-13)
2. Failure routing → review/DLQ — `test_failure_routing.py`
3. Queue-depth scaling — `test_queue_depth_scaling.py`
4. S3 Object Lock immutability — `test_object_lock.py` **+ live proof**

## NEXT GATE: v0.6.0 — CI/CD & Security Scanning
GitHub Actions `ci.yml` (fmt/validate/tflint/pytest) + `plan.yml` (plan-on-PR,
no auto-apply) · pip-audit · Grype · checkov · ruff · Lambda versions+aliases
rollback (DEC-6/8/9/10). **First step: create the GitHub remote** (push has been
deferred since v0.1.0 — this is where it lands). Opens on **GO**.

## REMAINING TO v1.0.0
- v0.6.0 CI/CD + security scanning
- v1.0.0 Capstone handoff package (DEC-11)
- Not gated but pending: full deploy (4 container images built+pushed + apply)
  for a live end-to-end run; only `audit_store` is currently live.

## DECISIONS SNAPSHOT
14 of 14 LOCKED. No open questions.
