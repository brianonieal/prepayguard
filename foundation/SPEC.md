# SPEC.md
# Current-gate detail. Updated each gate.

## LAST CLOSED: v0.2.0 — Component A (Payment Intake API + Idempotency)
**Status:** WORK COMPLETE, ALL CRITERIA MET — awaiting GO certification.
CONFIRMED ✓ · ROADMAP APPROVED ✓ · DEC-13 logged ✓ · build done ·
pytest 6/6 · fmt/validate/tflint green · checkov 271/0 · `terraform plan` clean
(77 add / 0 change / 0 destroy, us-east-2).

**Commitment 1 (idempotency) demonstrated:** DynamoDB atomic conditional write
with a PENDING→SENT state machine and original-result replay (DEC-13). Evidence:
`tests/test_idempotency.py` (6 cases, incl. the atomicity guard and the
crash-before-enqueue recovery). Handler: `src/component_a_intake/app.py`.

**Deferred (per CONFIRMED scope):** real ECR image push, first `terraform apply`,
and live smoke test — done when the live-AWS commitments (2 failure-routing,
3 queue-depth scaling) need standing infrastructure.

## NEXT GATE: v0.3.0 — Components B & C (Enrichment + Risk Scoring)
Two SQS-triggered workers on the shared `queue_worker_stage` module: B matches
payment data against reference sources; C scores risk and decides a disposition.
Opens on **GO**.

## DECISIONS SNAPSHOT
13 of 13 LOCKED (DEC-1..12 seeded from the decisions log; DEC-13 idempotency
backing store). No open questions.
