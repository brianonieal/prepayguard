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
| v0.1.0 | Terraform Foundation & Shared Module | All Terraform modules author-complete and `plan`-clean; `queue_worker_stage` built first as the dependency root; DECISIONS.md + foundation docs seeded | 10h | ~3.4h | DONE* (actual: 1.5) |
| v0.2.0 | Component A — Payment Intake API | IAM-authed API Gateway → Lambda performs payment-ID idempotency dedup and writes to output SQS. **Commitment 1** demonstrated. | 8h | ~2.7h | pending |
| v0.3.0 | Components B & C — Enrichment + Risk Scoring | Two SQS-triggered workers on the shared module: reference-match enrichment, then risk score + disposition decision. | 8h | ~2.7h | pending |
| v0.4.0 | Component D — Disposition, Audit, Notify | Immutable audit write to S3 Object Lock (**commitment 4**), ambiguous → review queue (**commitment 2**), webhook via least-priv Secrets Manager (DEC-7). | 9h | ~3.1h | pending |
| v0.5.0 | Queue-Depth Scaling & DLQ Hardening | Event-source-mapping batch/concurrency tuning (**commitment 3**), CloudWatch queue-depth alarms, DLQ + redrive across all stages. | 5–9h | ~1.7–3.1h | pending |
| v0.6.0 | CI/CD & Security Scanning | GitHub Actions `ci.yml` (fmt/validate/tflint/pytest) + `plan.yml` (plan-on-PR); pip-audit, Grype, checkov, ruff; Lambda versions+aliases rollback (DEC-6/8/9/10). | 6–12h | ~2.0–4.1h | pending |
| v1.0.0 | Capstone Deliverable | ARCHITECTURE.md (failure modes, known unknowns, rollback), rendered test report, deployment docs, security findings (narrative + risk table + raw-scan appendix), residual risks, follow-on work (DEC-11). | 8–16h | ~2.7–5.4h | pending |

**Total (post-calibration):** ~18–24h across 7 gates.

## NOTES
- *v0.1.0 closed on fmt/validate/tflint/checkov all green. `terraform plan` (one success criterion) is pending AWS credentials — aws CLI is not installed on this machine. Surfaced at gate close for Brian's decision; plan runs before the v0.2.0 apply work regardless.
- Every gate is backend/infra → flow is **CONFIRMED → ROADMAP APPROVED → GO** (no MOCKUPS/FRONTEND).
- Build order within v0.1.0 starts at `modules/queue_worker_stage/main.tf` (dependency root for B, C, D via `for_each`), per owner instruction.
- Graded commitments land across v0.2.0 (1), v0.4.0 (2, 4), v0.5.0 (3). Each with a passing test file before its gate closes.
- Handoff package (v1.0.0) draws from ARCHITECTURE.md, TESTS.md, INFRASTRUCTURE.md, SECURITY.md accumulated over prior gates — it is assembled, not written from scratch.
