# VERSION_ROADMAP.md
# Calibration: 0.34x multiplier applied (operator-level, 16 gates, HIGH confidence).
#   Source: ~/.claude/syntaris/calibration-profile.md, PAT-001.
#   CAVEAT: contributing projects (Test-App, Notes-App, Briefing Tool) are NOT
#   AWS/Terraform. The 0.34x bias was learned on other stacks, so it is a starting
#   point only. Later gates use ranges. Re-pull after 3 project gates close.
# Raw estimates are pre-multiplier. "Hours" column is post-calibration (raw x 0.34).
# Build type: internal / capstone. Final gate: v1.0.0 Capstone Deliverable.
# UI phases (MOCKUPS APPROVED / FRONTEND APPROVED) are N/A for every gate — backend only.
# STATUS: BUILD APPROVED — roadmap locked 2026-07-03. Roadmap-level changes require re-running BUILD APPROVED.

| Version | Name | Goal (user-facing outcome) | Raw | Hours (0.34x) | Status |
|---|---|---|---|---|---|
| v0.1.0 | Terraform Foundation & Shared Module | All Terraform modules author-complete and `plan`-clean; `queue_worker_stage` built first as the dependency root; DECISIONS.md + foundation docs seeded | 10h | ~3.4h | DONE (actual: 1.5) |
| v0.2.0 | Component A — Payment Intake API | IAM-authed API Gateway → Lambda performs payment-ID idempotency dedup and writes to output SQS. **Commitment 1** demonstrated. | 8h | ~2.7h | DONE (actual: 0.4) |
| v0.3.0 | Components B & C — Enrichment + Risk Scoring | Two SQS-triggered workers on the shared module: reference-match enrichment, then risk score + disposition decision. | 8h | ~2.7h | DONE (actual: 0.5) |
| v0.4.0 | Component D — Disposition, Audit, Notify | Immutable audit write to S3 Object Lock (**commitment 4**), ambiguous → review queue (**commitment 2**), webhook via least-priv Secrets Manager (DEC-7). | 9h | ~3.1h | DONE (actual: 0.7) |
| v0.5.0 | Queue-Depth Scaling & DLQ Hardening | Event-source-mapping batch/concurrency tuning (**commitment 3**), CloudWatch queue-depth alarms, DLQ + redrive across all stages. | 5–9h | ~1.7–3.1h | DONE (actual: 0.4) |
| v0.6.0 | CI/CD & Security Scanning | GitHub Actions `ci.yml` (fmt/validate/tflint/pytest) + `plan.yml` (plan-on-PR); pip-audit, Grype, checkov, ruff; Lambda versions+aliases rollback (DEC-6/8/9/10). | 6–12h | ~2.0–4.1h | DONE (actual: 0.7) |
| v1.0.0 | Capstone Deliverable | ARCHITECTURE.md (failure modes, known unknowns, rollback), rendered test report, deployment docs, security findings (narrative + risk table + raw-scan appendix), residual risks, follow-on work (DEC-11). | 8–16h | ~2.7–5.4h | DONE (actual: 1.5) |

**Total (post-calibration):** ~18–24h across 7 gates.

## PHASE 2 — "Treasury Console" frontend (BUILD APPROVED 2026-07-03)
AWS-native SPA (React/Vite on S3+CloudFront), Cognito auth → temp IAM creds →
SigV4 to the existing + new APIs. UI gates run the full 5-phase flow
(MOCKUPS/FRONTEND APPROVED apply again). Estimates held loose — no frontend
calibration data yet; first gate recalibrates.

| Version | Name | Goal | Est | Status |
|---|---|---|---|---|
| v1.1.0 | Console Foundation | Cognito pools + authed IAM role, S3+CloudFront shell, `reviews` DynamoDB table, Component D writes review items to it | ~1–2h | DONE (actual: 0.8) |
| v1.2.0 | Read/Action API | GET /reviews, GET /audit/{id}, POST /reviews/{id}/decision (3 Lambdas + API GW + tests) | ~1–2h | pending |
| v1.3.0 | Console UI | MOCKUPS APPROVED → FRONTEND APPROVED: login, submit form, review dashboard, audit detail, approve/reject | ~2–4h | pending |
| v1.4.0 | Integrate + Deploy → Console GA | SPA wired to Cognito+APIs, CloudFront deploy, live e2e (login → submit → flag → review) | ~1–2h | pending |

## NOTES
- v0.1.0 fully green: fmt/validate/tflint/checkov + `terraform plan` all clean. Plan ran in us-east-2 against account <ACCOUNT_ID>: **74 to add, 0 to change, 0 to destroy**, no errors/warnings. Region aligned us-east-1 → us-east-2 to match the operator's account before planning.
- Every gate is backend/infra → flow is **CONFIRMED → ROADMAP APPROVED → GO** (no MOCKUPS/FRONTEND).
- Build order within v0.1.0 starts at `modules/queue_worker_stage/main.tf` (dependency root for B, C, D via `for_each`), per owner instruction.
- Graded commitments land across v0.2.0 (1), v0.4.0 (2, 4), v0.5.0 (3). Each with a passing test file before its gate closes.
- Handoff package (v1.0.0) draws from ARCHITECTURE.md, TESTS.md, INFRASTRUCTURE.md, SECURITY.md accumulated over prior gates — it is assembled, not written from scratch.
