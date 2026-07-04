# MEMORY_EPISODIC.md — PrePayGuard ("Treasury")
# Session and gate history. Newest first.

## GATE OUTCOMES

| Date | Gate | Outcome | Est (raw/cal) | Actual | Notes |
|---|---|---|---|---|---|
| 2026-07-03 | v0.1.0 Terraform Foundation & Shared Module | WORK COMPLETE, all criteria met — awaiting GO | 10h / ~3.4h | ~1.5h | fmt/validate/tflint/checkov green (270/0) + `terraform plan` clean in us-east-2 (74/0/0, acct <ACCOUNT_ID>). Latent v0.4.0 KMS bug fixed pre-emptively. |
| 2026-07-03 | v0.2.0 Component A — Payment Intake API + Idempotency | WORK COMPLETE, all criteria met — awaiting GO | 8h / ~2.7h | ~0.4h | Commitment 1 demonstrated (DEC-13: DynamoDB conditional write + PENDING→SENT + replay). pytest 6/6, checkov 271/0, plan 77/0/0. Critical-thinker caught 2 HIGH design holes pre-code. |
| 2026-07-03 | v0.3.0 Components B & C — Enrichment + Risk Scoring | WORK COMPLETE, all criteria met — awaiting GO | 8h / ~2.7h | ~0.5h | DEC-14 screening domain (bundled synthetic DNP list, match→score→3-way disposition). pytest 14/14, checkov 271/0, plan 77/0/0 (no .tf change). Grounding workflow killed early for efficiency. |
| 2026-07-03 | v0.4.0 Component D — Disposition, Audit, Notify | CLOSED (tagged) | 9h / ~0.8h (proj-cal) | ~0.7h | Commitments 2 & 4 + DEC-7. pytest 26/26. LIVE Object-Lock proof PASS on real bucket (delete+shorten AccessDenied). audit_store deployed (9 res, first real spend). plan 68/0/0, 0 drift. |
| 2026-07-03 | v0.5.0 Queue-Depth Scaling & DLQ Hardening | CLOSED (tagged) | 5–9h / ~0.5h (proj-cal) | ~0.4h | Commitment 3 (config proof via terraform show -json). ALL 4 commitments now done. pytest 29/29. No .tf change. |
| 2026-07-03 | v0.6.0 CI/CD & Security Scanning | CLOSED (tagged) | 6–12h / ~0.7h (proj-cal) | ~0.7h | DEC-6/8/9/10. Private repo github.com/brianonieal/prepayguard. CI GREEN on Actions (both jobs). ruff+pip-audit clean. Push needed explicit user authorization (publish guardrail). |
| 2026-07-03 | v1.0.0 Capstone Deliverable / Full Deploy | CLOSED (tagged) — PROJECT COMPLETE | 8–16h / ~1.5h (proj-cal) | ~1.5h | Full live deploy (us-east-2), e2e run demonstrated all 4 commitments LIVE. DEC-11 handoff package (md+docx). 2 deploy-only fixes (OCI manifest, API GW account role). Guardrails handled: publish, blind-apply, external secret write. |
| 2026-07-03 | v1.1.0 Console Foundation (Phase 2) | CLOSED (tagged) | ~1–2h | ~0.8h | Cognito→IdentityPool→authed role (DEC-5 reuse), CloudFront shell live (d2rbxaf6pqgvb1.cloudfront.net), reviews table, D v1.1.0 redeployed (alias→v2, DEC-10 real). Live smoke: review→table pending. pytest 31/31, checkov 265/0. |

| 2026-07-04 | v1.2.0 Console Read/Action API (Phase 2) | CLOSED (tagged) | ~1–2h | ~0.7h | Router Lambda + IAM REST API (console role only). Reviewer decisions audited to Object Lock. Deployed (18 res) + prod smoke 200s. pytest 37/37, checkov 410/0. |

| 2026-07-04 | v1.3.0 Console UI (Phase 2) | CLOSED (tagged) | 2–4h | ~1.6h | React/Vite SPA, 4 screens + batch CSV + profile/settings/user-menu + tier-1 (client hash-verify, deep links, search, score explainability) + polish. vitest 15/15, build clean. Static (fake data); wiring is v1.4.0. |

| 2026-07-04 | v1.4.0 Console GA (Phase 2) | CLOSED (tagged) — CONSOLE LIVE | ~2–3h | ~2.5h | Amplify+aws4fetch auth (DEC-15), attachments backend, CORS, D v1.4.1. Deployed to CloudFront (d2rbxaf6pqgvb1). LIVE e2e PASS (Cognito→creds→SigV4→submit→review→decide). Fixed tf-manages-index.html drift. |

| 2026-07-04 | v1.5.0 Read-Scale Hardening (Phase 2) | CLOSED (tagged) | ~1–2h | ~1.0h | Reviews GSI + paginated query (cursor); audit_index table (D writes every disposition) -> O(1) GET /audit w/ prefix-scan fallback; frontend Load-more. Redeployed D+console_api. Live e2e PASS + pagination verified. |

| 2026-07-04 | v1.6.0 Write-Scale Hardening (Phase 2) | CLOSED (tagged) | ~2–3h | ~2.0h | Component E S3-triggered batch ingest reusing A's idempotency store+queue (DEC-16); intra-file+cross-path dedup; batches table+endpoints; bulk decision (per-item audit); frontend batch-upload + multi-select. Caught+fixed an intra-file dup bug pre-deploy. Live PASS (dedup + bulk). |

| 2026-07-04 | v2.0.0 Roles & Segregation of Duties (Phase 3) | CLOSED (tagged) | ~2–3h | ~2.5h | Cognito groups->IAM roles via Token role-mapping; edge authz (submitter->batch routes only); app-level SoD (approver != submitter, single+bulk) proven live; console role-gating. Hit the known IAM-propagation resource-policy error -> re-apply. |

| 2026-07-04 | v2.1.0 Reference-Data Lifecycle (Phase 3) | CLOSED (tagged) | ~2–3h | ~1.5h | Versioned S3 reference store + admin publish path + audit citation (reference_list_version). Live: v2-only entry flagged, audit cites v2, reviewer 403, v1 history intact. checkov count drop investigated -> module-attribution dedup, coverage verified by resource count. |

| 2026-07-04 | v2.1.2 Multi-Format Batch Ingestion (Phase 3, inserted) | CLOSED (tagged) | ~1–2h | ~1.0h | CSV+XLSX+JSON batch parsing (shared validator), unsupported reported; S3 trigger on all uploads; multi-format Submit. Live PASS via real presigned-PUT browser path (xlsx/json ingest, pdf unsupported). |

| 2026-07-04 | v2.2.0 Semantic Payee Matching (Phase 3) | CLOSED (tagged) | ~3–4h | ~2.0h | Bedrock embeddings, cosine-in-store (no vector DB, ~$0 vs OpenSearch ~$700/mo), semantic->review, versioned vectors, degrade-on-error. Live tuned: clean ~0.24 vs variants 0.86-0.97, 0.72 splits; 'Globex Overseas Incorporated' caught semantically (string missed). |

| 2026-07-04 | v2.3.0 LLM Adjudication Briefs (Phase 3) | CLOSED (tagged) | ~2–3h | ~1.5h | On-demand, read-only, grounded advisory briefs (Nova Lite/Converse); never written to the audit record (verified live); reviewer-triggered button + disclaimer; degrade-on-error. |

| 2026-07-04 | v2.4.0 Analytics & Compliance (Phase 3 FINAL) | CLOSED (tagged) | ~2–4h | ~2.5h | Oversight dashboard + auditor CSV export over audit_index/reviews; read-only auditor role (edge GET-only). Live: 178 screened, 23.6% hit; admin+auditor see analytics, auditor decision 403, reviewer analytics 403. **Locked roadmap v0.1.0->v2.4.0 COMPLETE.** |

## SESSIONS

### 2026-07-03 — Session 1: project bootstrap → v0.1.0 build
- /start → new project; Phase 1 brain dump supplied as two files
  (TREASURY_PROJECT_BRIEF.md + TREASURY_DECISIONS_LOG.md); no re-interrogation.
- 12 decisions seeded verbatim into DECISIONS.md as LOCKED.
- BUILD APPROVED: 7-gate roadmap v0.1.0 → v1.0.0 (0.34x operator calibration,
  with stated caveat that the pool contains no AWS/Terraform projects).
- Phases 4/5 (mockups/frontend) marked N/A permanently — backend-only project.
- v0.1.0: CONFIRMED → ROADMAP APPROVED → built (queue_worker_stage first per
  Brian's instruction) → verification green → gate-close docs written.
- Background grounding workflow (8 agents) verified provider syntax before HCL
  was written; its HIGH finding (aws_ecr_image.id vs image_digest) recorded in
  ARCHITECTURE.md known-unknowns for v0.2.0.
- Toolchain installed project-locally (.tools/bin: terraform 1.15.7,
  tflint 0.63.1; checkov via pip). aws CLI 2.35.15 installed by Brian
  (default path; not on Git Bash PATH — Terraform reads ~/.aws/credentials
  directly regardless). IAM user treasury-cli + AdministratorAccess.
- Region aligned us-east-1 → us-east-2; `terraform plan` clean (74/0/0).

### 2026-07-03 — Session 1 (cont.): v0.2.0 Component A
- v0.2.0: CONFIRMED → /critical-thinker on the idempotency store (DEC-13) →
  ROADMAP APPROVED → test-first build → green.
- Critical-thinker (isolated subagent) surfaced two HIGH design holes before any
  code: reject-vs-replay, and a two-phase silent-loss window. Both closed in the
  design and turned into test cases.
- Chose hand-rolled DynamoDB conditional write + status field over AWS Lambda
  Powertools (visible mechanism = stronger commitment-1 evidence); reversible.
- Test deps installed: pytest 9.1.1, moto 5.2.2, boto3 1.35.49 (user site).
