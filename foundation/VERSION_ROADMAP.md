# VERSION_ROADMAP.md
# Calibration: 0.34x multiplier applied (operator-level, 16 gates, HIGH confidence).
#   Source: operator calibration profile (PAT-001).
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
| v1.2.0 | Read/Action API | GET /reviews, GET /audit/{id}, POST /reviews/{id}/decision (1 router Lambda + API GW + tests) | ~1–2h | DONE (actual: 0.7) |
| v1.3.0 | Console UI | login, submit (+ batch CSV upload), review dashboard w/ stat cards, audit detail, approve/reject; **tier-1 folded in** (hash-verify, deep-link routing, search/filters, score explainability); **polish + profile/settings/user-menu**. Interactive app reviewed as the mockup artifact. | ~2–4h | DONE (actual: 1.6) |
| v1.4.0 | Integrate + Deploy → Console GA | SPA wired to Cognito+APIs, CloudFront deploy, live e2e (login → submit → flag → review); attachments backend (presigned S3 uploads) | ~2–3h | DONE (actual: 2.5) |
| v1.5.0 | Read-Scale Hardening | Reviews GSI (status/received_at) + paginated `GET /reviews?status=&limit=&cursor=`; `payment_id`-indexed audit lookup (audit_index table; D writes for every disposition) → O(1) `GET /audit`; frontend pagination + server-side status filter. | ~1–2h | DONE (actual: 1.0) |
| v1.6.0 | Write-Scale Hardening | S3 batch-file ingestion (presigned upload → S3-triggered Lambda → idempotent enqueue + batch summary, replacing the client-side loop); bulk review actions (batch decision endpoint + multi-select UI). | ~2–3h | DONE (actual: 2.0) |

## PHASE 3 — "Do-Not-Pay Intelligence" (BUILD APPROVED 2026-07-04)
Adds the AI/ML layer the capstone is named for + the realism gaps around it. All
AWS-native (Bedrock, Cognito, DynamoDB/S3); stack unchanged. Sequenced by
DEPENDENCY, not marquee: roles gate the admin/analytics surfaces; the managed
reference store underpins semantic matching; briefs explain semantic hits;
analytics synthesizes. Estimates sit in the ~1–4h integration band (recent
actuals: v1.4.0 2.5, v1.5.0 1.0, v1.6.0 2.0); the two Bedrock gates carry the
most uncertainty (unfamiliar API + mocking LLM/embeddings in tests).

| Version | Name | Goal | Est | Status |
|---|---|---|---|---|
| v2.0.0 | Roles & Segregation of Duties | Cognito groups (submitter/reviewer/admin) → per-group IAM roles; intake + console APIs authorize by group; **app-level SoD: an approver cannot approve a payment they submitted**. Console gates nav/actions by role. | ~2–3h | DONE (actual: 2.5) |
| v2.1.0 | Reference-Data Lifecycle | Screening lists move from bundled to a managed, **versioned** store (DynamoDB/S3); admin-gated update path; each screening record cites the reference list version it matched. | ~2–3h | DONE (actual: 1.5) |
| v2.1.2 | Multi-Format Batch Ingestion | Batch upload accepts CSV + Excel (.xlsx) + JSON; non-tabular files reported "unsupported", never dropped. Inserted gate (owner request); v2.1.1 was the CORS hotfix. | ~1–2h | DONE (actual: 1.0) |
| v2.2.0 | Semantic Payee Matching | Bedrock embeddings in enrichment: a match is exact-rule OR semantic similarity ≥ threshold over the managed reference set. Vector store settled at gate (cosine-in-DDB proposed vs OpenSearch Serverless). | ~3–4h | DONE (actual: 2.0) |
| v2.3.0 | LLM Adjudication Briefs | Bedrock generates an evidence-grounded "why flagged / recommended action" for reviewers. **Advisory only — NOT part of the immutable decision record; the human still decides.** | ~2–3h | DONE (actual: 1.5) |
| v2.4.0 | Analytics & Compliance Reporting | Throughput / hit-rate / disposition / aging dashboard + auditor export & legal-hold view over the audit log; role-gated (admin/auditor). | ~2–4h | DONE (actual: 2.5) — **FINAL: locked roadmap complete** |

**Phase 3 total (calibrated):** ~11–17h across 5 gates.

## PHASE 4 — "Showcase & Demo Readiness" (BUILD APPROVED 2026-07-04)
Built to show the live product to a Treasury exec + the professor, and to make the
console's remaining demo-chrome real. Stack unchanged (React/Vite console + a lean
console_api endpoint). Recent gates run ~40–50% under estimate.

| Version | Name | Goal | Est | Status |
|---|---|---|---|---|
| v3.0.0 | Executive Showcase | New console tab (reviewer/admin/auditor): high-polish narrative of what PrePayGuard is, how it decides, and what it did — hand-built SVG charts (disposition donut, throughput timeline, hit-rate, match-type, pipeline flow), balanced exec+professor prose, worked approve/review/reject examples with evidence. Live data via a lean `GET /showcase`. | ~3–4h | DONE (actual: ~1.5) — live: /showcase 200, 178 screened, all 3 worked examples resolved |
| v3.1.0 | Demo Controls | Admin-only "Clear data" in Settings: resets the working views (reviews / audit_index / batches / idempotency) for a clean demo slate, behind a typed confirmation; the immutable S3 audit stays under Object Lock (surfaced as the compliance point). | ~1.5–2h | DONE (actual: ~1.5) — live: reset 200, 420 cleared, all dashboards zero, 217 audit objects intact |
| v3.2.0 | Console Depth | Make the remaining chrome real: Profile loads real ID-token fields + working Change Password and MFA (TOTP) via Amplify; Settings persists prefs honestly (no fake/inert toggles). Remove every dead button. | ~2–3h | DONE (actual: ~1.5) — real Profile (token fields + password + TOTP enroll), Login TOTP challenge, pool OPTIONAL MFA live, inert toggles removed |
| v3.3.0 | Automated Real-Data Feed | Component F (scheduled feeder, DEC-23): EventBridge triggers a Lambda that pulls real USAspending awards, drops a file in the batch bucket, Component E ingests, the pipeline screens. No manual upload. Honest feed plus a labeled manual demo-positive; `feeder_enabled` stop switch. Now on a business-hours Eastern schedule (9am-5pm ET, 7 days). | ~2-3h | DONE, DEPLOYED LIVE 2026-07-06 (verified e2e: real payees auto-approved, demo-positive flagged via semantic) |
| v3.4.0 | Automated Reference Refresh | Component G (scheduled refresher, DEC-24): EventBridge Scheduler daily re-pulls the real SAM.gov exclusions, re-embeds, and republishes the versioned reference document only when the list changed. Keeps the Do Not Pay watchlist current on its own. `refresher_enabled` stop switch. | ~2-3h | DONE, DEPLOYED LIVE 2026-07-06 (verified: unchanged->skip guard, schedule ENABLED daily 6am ET) |
| v3.5.0 | In-Console Feed Control | Admin Feed tab (DEC-25): a USAspending-style builder (award types, look-back window, per-pull size) that Saves the feeder's query for the schedule and Runs it on demand. Console + console API + feeder, admin-only. | ~3-4h | DONE, DEPLOYED LIVE 2026-07-06 (feeder honors inline config; Feed tab live) |
| v3.6.0 | Full Feed Builder | Extend the Feed tab (DEC-26) to the full USAspending search surface: award types incl. IDVs + Prime/Sub toggle, awarding/funding agency + sub-agency, location, date type + from/to range. Agency lists fetched keyless from USAspending. | ~3-4h | BUILT + verified locally (pytest 135/135, vitest 34/34, checkov 662/0); live deploy pending |
| v3.7.0 | Console Restructure | Collapse 6 tabs into Dashboard (flagged hero + Overview) / Review Queue / Audit log; Reference Data + Feed + Demo controls under an Admin dropdown; Submit -> header button + modal; role-aware landing (DEC-27). Frontend-only. | ~3-4h | BUILT + verified locally (vitest 34/34; backend unchanged); live deploy pending |

**Phase 4 total (calibrated):** ~7-9h across 3 gates, **actual ~4.5h. Phase 4 COMPLETE (2026-07-04).** v3.3.0 Automated Real-Data Feed added 2026-07-06 (DEC-23). (Optional Notifications, a real SES email digest, still deferred unless requested.)

## NOTES
- v0.1.0 fully green: fmt/validate/tflint/checkov + `terraform plan` all clean. Plan ran in us-east-2 against account <ACCOUNT_ID>: **74 to add, 0 to change, 0 to destroy**, no errors/warnings. Region aligned us-east-1 → us-east-2 to match the operator's account before planning.
- Every gate is backend/infra → flow is **CONFIRMED → ROADMAP APPROVED → GO** (no MOCKUPS/FRONTEND).
- Build order within v0.1.0 starts at `modules/queue_worker_stage/main.tf` (dependency root for B, C, D via `for_each`), per owner instruction.
- Graded commitments land across v0.2.0 (1), v0.4.0 (2, 4), v0.5.0 (3). Each with a passing test file before its gate closes.
- Handoff package (v1.0.0) draws from ARCHITECTURE.md, TESTS.md, INFRASTRUCTURE.md, SECURITY.md accumulated over prior gates — it is assembled, not written from scratch.
