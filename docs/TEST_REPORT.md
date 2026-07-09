# Test report — PrePayGuard

**Date:** 2026-07-09. **Result: `152 passed, 1 xfailed`** (the 1 xfail is a *deliberately*
documented known limitation, see below — not a failure). Reproduce: `pytest` from the repo root
(hermetic — `moto`/local fakes, no live AWS; runs in CI, `.github/workflows/ci.yml` `python` job).
Runtime ≈ 90 s.

This is the rendered summary; raw pytest output is in `docs/HANDOFF.md` Appendix A.

## By test file

| Test file | Tests | Area |
|---|---|---|
| `test_console_api.py` | 47 | Console API: reviews, audit read, decisions (maker/checker), batches, reference publish, feed config, LLM brief, analytics |
| `test_sam_ingest.py` | 14 | Real SAM.gov exclusions ingest (schema drift, active-only, dedupe, size cap) |
| `test_feeder.py` | 15 | Component F feeder (USAspending pulls, filters, page-1 fix) |
| `test_component_e.py` | 11 | Component E batch ingest (CSV/Excel/JSON → A's queue) |
| `test_enrichment.py` | 11 | Component B matching: TIN/exact/fuzzy/semantic |
| `test_intake_validation.py` | 8 | **2.1e payee validation** — evasion payloads 400'd, fail-closed, residual passes (known limit) |
| `test_idempotency.py` | 6 | **Commitment 1** — payment-ID idempotency |
| `test_failure_routing.py` | 6 | **Commitment 2** — failure → DLQ/redrive → review routing |
| `test_review_notification.py` | 6 | **Commitment 2** — review-queue routing + webhook notify |
| `test_semantic_eval.py` | 5 | Eval-harness reproducibility (deterministic, no Bedrock) |
| `test_refresher.py` | 5 | Component G refresher (re-embed, republish on change) |
| `test_injection_resistance.py` | 4 | **Brief invariants (2.2)** + the F1 residual xfail |
| `test_risk_scoring.py` | 4 | Component C scoring + disposition bands |
| `test_object_lock.py` | 4 | **Commitment 4** — Object Lock immutability (config, moto) |
| `test_queue_depth_scaling.py` | 3 | **Commitment 3** — max-concurrency + queue-depth alarm |

(149 `def test_` functions; parametrization expands to 152 passed + 1 xfailed.)

## The four graded commitments

| Commitment | Status | Test file | Evidence beyond unit tests |
|---|---|---|---|
| 1 — payment-ID idempotency | **PROVEN** | `test_idempotency.py` (6) | conditional-write replay; live e2e in HANDOFF §2.2 |
| 2 — failure → human review (DLQ/redrive) | **PROVEN** | `test_failure_routing.py` (6) + `test_review_notification.py` (6) | per-stage DLQ + `ReportBatchItemFailures` |
| 3 — queue-depth scaling + alarm | **PROVEN** | `test_queue_depth_scaling.py` (3) | max-concurrency + `ApproximateNumberOfMessages` alarm |
| 4 — Object Lock immutability | **PROVEN (config) + live-verified once** | `test_object_lock.py` (4) | see moto caveat |

**Object Lock — moto caveat (stated, not hidden):** the unit tests assert the **configuration**
(COMPLIANCE mode, retention) under `moto`, which does not fully enforce COMPLIANCE deletion
semantics. The gold-standard immutability proof is the **live** script
`scripts/live_object_lock_proof.py` run against a real Compliance-mode bucket (verified once at
v0.4.0). Documented at `tests/test_object_lock.py:3-4` and `foundation/TESTS.md:24`.

## The one xfail — a documented limitation, not a failure

`test_injection_resistance.py::test_residual_short_name_append_still_evades` is
`@pytest.mark.xfail(strict=True)`. It asserts the *desired* behavior — that a listed entity
(`Acme Shell LLC`) is still screened when a payer submits `Acme Shell LLC OK PAY` — and is
**expected to fail**, because the F1 residual (a short in-budget append) evades the whole-string
matcher even with 2.1e validation on. `strict=True` means if it ever XPASSes (someone silently
"fixes" it), the suite fails loudly. This is the F1 residual made executable; see
`docs/sme/INJECTION_THREAT_MODEL.md` and `docs/evidence/EVAL_REPORT.md`.

## Static analysis (same run, dated artifacts in `docs/evidence/scans/`)

ruff **pass** · pip-audit **8/8 clean** · tflint **clean** · checkov **662 / 0 / 3** ·
ECR image scan **2 HIGH + 1 MED + 1 LOW per image** (base-image CVEs — HANDOFF §4.1 row 12).
