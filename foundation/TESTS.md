# TESTS.md
# Test strategy. Locked under BUILD APPROVED; per-gate test tasks fold into ROADMAP APPROVED.

## RUNNERS
- **pytest** — all application/handler tests and evidence tests. (No vitest/playwright — backend only, no UI.)
- **Terraform validation** in CI — `terraform fmt -check`, `terraform validate`, `tflint`, `checkov` (not pytest, but gate-blocking).

## COVERAGE TARGETS
- **Critical path:** the four graded commitments + DEC-7 notification each have a dedicated passing test. These are non-negotiable — a commitment without a passing test does not count as demonstrated.
- **Handler logic:** 90%+ on the disposition/idempotency/scoring decision code (the parts that decide a payment's fate).
- **Infra:** validated via `terraform validate` + `checkov` in CI rather than unit-tested.

## EVIDENCE TEST REGISTRY (maps to graded commitments)
| Test file | Demonstrates | Gate |
|---|---|---|
| `tests/test_idempotency.py` | Commitment 1 — payment-ID dedup (same ID twice → one downstream message) | v0.2.0 |
| `tests/test_failure_routing.py` | Commitment 2 — component failure / ambiguous disposition routes to human review | v0.4.0 |
| `tests/test_object_lock.py` | Commitment 4 — audit record is immutable (overwrite/delete denied under Compliance mode) | v0.4.0 |
| `tests/test_review_notification.py` | DEC-7 — webhook posted on review routing; secret retrieved via scoped `GetSecretValue` | v0.4.0 |
| `tests/test_queue_depth_scaling.py` | Commitment 3 — queue depth drives worker concurrency/batch scaling | v0.5.0 |

## POLICY
- **Test-first where it's cheap:** commitment tests are written to define expected behavior before the handler is complete (test-writer subagent at gate open), not retrofitted to pass on an empty function.
- **AWS boundary:** unit tests use `moto`/local fakes or dependency injection so they run in CI without live AWS. Object Lock immutability is asserted against `moto` behavior and documented; a note flags where local-fake behavior diverges from real Compliance-mode semantics (real immutability is also verified once against a live dev bucket during v0.4.0).
- **Enforcement:** `/validate` at every GATE CLOSE. Any evidence test failing blocks the gate. Rendered test report (DEC-11) generated at v1.0.0 from the accumulated suite.
- **Regression:** once a commitment test passes, it stays in the suite and must keep passing at every subsequent gate close.
