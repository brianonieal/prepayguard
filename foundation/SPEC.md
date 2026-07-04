# SPEC.md
# Current-gate detail.

## v3.2.0 — Console Depth (2026-07-04, live) · Phase 4 gate 3/3 · FINAL
The remaining chrome is real; Phase 4 complete. Frontend + Cognito-pool only, no backend.

- **Profile** (rewritten): identity/account from the ID token (sub, email, role, auth_time,
  iat). Working Change password (Amplify updatePassword) + TOTP MFA enrollment
  (setUpTOTP → shared secret → verifyTOTPSetup + updateMFAPreference PREFERRED) + Disable;
  live status via fetchMFAPreference. Dead display-name/Save removed.
- **Login**: handles CONFIRM_SIGN_IN_WITH_TOTP_CODE (confirmSignIn) so enrolling can't lock
  a user out; no-MFA login unchanged.
- **Settings**: inert Email-digest / Assignment-alerts toggles removed (no backend; that's
  deferred v3.3.0). Density + default filter + admin Demo controls remain.
- **Cognito pool**: mfa_configuration OPTIONAL + software_token_mfa enabled (opt-in, in-place).
- Verified: vitest 31/31 (+3), pytest 90/90 (unchanged), build clean, plan 0-drift, CORS
  green; **LIVE**: pool MFA OPTIONAL/TOTP true, SPA deployed, Profile harness-verified.
  Password/MFA round-trips need a real browser + authenticator (enroll on a non-admin
  account first). No new DECISION.

## v3.1.0 — Demo Controls (2026-07-04, live) · Phase 4 gate 2/3
Admin-only "Clear data" that zeroes the working data for a clean demo; the immutable
audit survives (the compliance point). Repeatable.

- **console_api** `POST /admin/reset` (admin-only; body `{"confirm":"RESET"}` or 400):
  generic `_clear_table` (key discovered from schema, paginated batch-delete) empties
  reviews / audit_index / batches / idempotency; returns per-table counts. S3 Object
  Lock audit records intentionally untouched.
- **IAM**: +BatchWriteItem +DescribeTable on the three tables + a new IdempotencyReset
  statement; idempotency name/ARN wired from module.api_intake; env IDEMPOTENCY_TABLE.
- **Console**: Settings "Demo controls" (admin-only danger zone) — typed-RESET gate,
  shows counts, states what clears vs. the immutable audit.
- Verified: pytest 39/39, vitest 28/28, build clean, plan 0-drift, CORS green;
  **LIVE**: guards 403/400 (no delete), then real reset 200 / 420 cleared / all
  dashboards zero / 217 audit objects still locked in S3.
- Deploy-only IAM lesson: key_schema needs DescribeTable, batch_writer needs
  BatchWriteItem (moto skips IAM, so tests missed both). No new DECISION (reinforces DEC-4).

## v3.0.0 — Executive Showcase (2026-07-04, live) · Phase 4 gate 1/3
A new "Overview" console tab that tells the PrePayGuard story to an exec + a professor, over live data.

- **console_api** `GET /showcase` (reviewer/admin/auditor; submitters edge-blocked):
  shared `_compute_summary()` (same aggregate as `/analytics`) + a **match-type tally**
  and **one worked example per disposition**, both from a bounded 40-record sample of
  recent audit records (full match detail lives in S3, not audit_index); missing
  dispositions backfilled from the full index. No new IAM; rides existing GET grants.
- **Console**: `Showcase.jsx` Overview tab — hero + live stats, SVG pipeline-flow
  diagram, decision-model explainer (harm-asymmetry), live metrics (donut / gauge /
  timeline / match-type bars, all hand-built SVG), three real worked examples,
  semantic + LLM section, trust/compliance section. Gated to `canReview`.
- Verified: pytest 87/87, vitest 26/26, build clean, plan 0-drift, CORS green;
  **LIVE**: /showcase 200, 178 screened / 23.6% hit, 3 worked examples resolved
  (approve/review name_exact 60/reject tin 95). All 6 images repointed → v3.0.0.
- No new DECISION (read-only endpoint + UI).

## v2.4.0 — Analytics & Compliance Reporting (2026-07-04, live) · Phase 3 gate 5/5 · FINAL
Oversight dashboard + auditor export; the locked roadmap is complete.

- **console_api** `GET /analytics` (mix/throughput/hit-rate over audit_index +
  queue/reviewer metrics over reviews) + `GET /audit-log` (filterable, CSV export),
  admin+auditor gated. New read-only **auditor** role, edge method-scoped to GET.
- **Console**: Analytics dashboard (CSS bars, no chart lib); auditor gets a
  read-only Review Queue (decide controls hidden).
- Verified: pytest 85/85, vitest 24/24, checkov 530/0, plan 0-drift, CORS green;
  **LIVE**: 178 screened / 23.6% hit; admin+auditor analytics 200, auditor
  decision 403, reviewer analytics 403.
- 21 decisions LOCKED (DEC-21). **Roadmap v0.1.0 → v2.4.0 COMPLETE.**

## v2.3.0 — LLM Adjudication Briefs (2026-07-04, live) · Phase 3 gate 4/5
Reviewers get an evidence-grounded AI brief — advisory, never in the audit record.

- **console_api** `GET /reviews/{id}/brief`: read-only; loads the audit record,
  grounds a prompt in its evidence, Bedrock Nova Lite via Converse. 404 no record;
  502 on model error. Never written to S3/audit/decision (DEC-20, verified live).
- **Console**: reviewer-triggered "Get AI brief" panel + advisory disclaimer.
- Verified: pytest 82/82, vitest 21/21, checkov 0-failed, plan 0-drift, CORS green;
  **LIVE**: brief cited the SAM name match + score 60 + INVESTIGATE; confirmed
  absent from the audit record.
- 20 decisions LOCKED (DEC-20).

## v2.2.0 — Semantic Payee Matching (2026-07-04, live) · Phase 3 gate 3/5
Catches payee variants that exact + fuzzy string matching miss (Bedrock embeddings).

- **Cosine-in-store** (DEC-19): console_api embeds each entry on publish, stores
  the vector in the versioned doc; B embeds the payee only when string rules miss,
  cosine ≥ threshold (0.72, versioned) → `name_semantic` match, capped to REVIEW.
  Bedrock failure degrades to rule-based screening. No vector DB (~$0 vs ~$700/mo).
- **Console**: AuditDetail shows semantic similarity.
- Verified: pytest 79/79, vitest 20/20, checkov 0-failed, plan 0-drift, CORS green;
  **LIVE**: "Globex Overseas Incorporated" (difflib 0.55) → name_semantic 0.857 →
  review, audit cites v3.
- 19 decisions LOCKED (DEC-19).

## v2.1.2 — Multi-Format Batch Ingestion (2026-07-04, live) · Phase 3 (inserted)
Batch upload takes CSV + Excel + JSON; unsupported files are reported.

- **Component E**: one shared `_build_row` validator behind `_parse_csv` /
  `_parse_xlsx` (openpyxl) / `_parse_json`; unsupported extension → `format:
  unsupported`, rejected (never dropped). `format` added to the batch summary.
- **S3 trigger** fires on all `batch-imports/` uploads (no suffix filter);
  `_presign_batch` accepts any safe filename.
- **Console**: picker accepts all files; CSV/JSON preview client-side, XLSX
  server-parsed; summary shows the format.
- Verified: pytest 74/74, vitest 20/20, checkov 0-failed, plan 0-drift, CORS
  guard green; **LIVE** xlsx/json ingest + pdf→unsupported via presigned-PUT.

## v2.1.0 — Reference-Data Lifecycle (2026-07-04, live) · Phase 3 gate 2/5
Every screening cites the exact list version it matched.

- **Versioned S3 store** (`reference/current.json` + immutable `versions/{N}.json`);
  Terraform owns the bucket, publishes own the documents; v1 seeded by script.
- **B** fetches with a 60s TTL and stamps `reference_version`; **D** writes
  `provenance.reference_list_version` into every audit record.
- **console_api:** GET/PUT `/reference` (admin-only: edge Deny + handler check,
  If-None-Match version claim) + version history endpoints.
- **Console:** admin-only Reference Data screen (edit + publish + history);
  AuditDetail shows the citation. Reviewer demo account added (owner-approved).
- Verified: pytest 69/69, vitest 18/18, checkov 0-failed (coverage re-verified),
  plan 0-drift; **LIVE**: v2-only entry flagged, audit cites v2, reviewer 403.
- 18 decisions LOCKED (DEC-18: versioned S3 reference document).

## v2.0.0 — Roles & Segregation of Duties (2026-07-04, live) · Phase 3 gate 1/5
Who submits ≠ who approves.

- **Cognito groups → per-group IAM roles** (submitter/reviewer/admin) via
  Identity-Pool Token role-mapping; no-group users fall back to a no-access role.
- **Edge authz:** reviewer+admin → all routes; submitter → batch routes only.
- **SoD:** A stamps `submitted_by` (cognitoIdentityId) → D persists it →
  console_api `_apply_decision` returns 403 when decider == submitter (single + bulk).
- **Console:** role from `cognito:groups` gates nav/actions; topbar role chip.
- Verified: pytest 60/60, vitest 15/15, checkov 502/0, plan 0-drift; **LIVE**
  brian(admin via mapping) self-approve→403, cross-identity→200.
- 17 decisions LOCKED (DEC-17: roles + SoD).

## v1.6.0 — Write-Scale Hardening (2026-07-04, live)
Batch ingestion moved server-side; reviewers act in bulk.

- **Component E — Batch Ingest** (new S3-triggered Lambda): CSV → `batch-imports`
  bucket → `ObjectCreated` → parse + idempotent enqueue reusing **Component A's**
  idempotency table + intake queue (**DEC-16**). Intra-file *and* cross-path
  dedup; per-file summary in the `batches` table.
- **console_api:** `POST /batches` (presign), `GET /batches/{id}` + `GET /batches`
  (poll), **`POST /reviews/decisions`** (bulk, ≤50, one audit record each).
- **Frontend:** Submit uploads the CSV once and polls the summary; review queue
  gains multi-select + a bulk Approve/Reject bar.
- Verified: pytest 56/56, vitest 13/13, checkov 472/0, plan 0-drift; **LIVE**
  batch summary queued=2/duplicate=1 (dedup proven) + bulk approve.
- 16 decisions LOCKED (DEC-16: batch ingest reuses the intake idempotency store).

## v1.5.0 — Read-Scale Hardening (2026-07-04, live)
Reviews and audit lookups now scale past a full-table Scan.

- **Reviews GSI** `status-received_at-index`: `GET /reviews?status=&limit=&cursor=`
  queries by status, newest-first, paginated (base64 `next_cursor`); falls back to
  a Scan only when no status filter is given.
- **Audit index** table (`payment_id`→`audit_key`): Component D writes it for every
  disposition, so `GET /audit/{id}` is a GetItem→GetObject (O(1)); a prefix-scan
  fallback keeps pre-index records resolvable.
- **Frontend:** review queue has a server-side status filter + "Load more"
  paginator; search stays client-side over the loaded page.
- Verified: backend pytest 43/43, console vitest 12/12, checkov 423/0, plan
  0-drift, and a LIVE e2e + live pagination/index check.

## PHASE 2 COMPLETE — Treasury Console GA (v1.4.0, 2026-07-04)
The console is **live and end-to-end verified**. Phase 2 (v1.1.0 → v1.4.0) done.

- **Live:** https://d2rbxaf6pqgvb1.cloudfront.net — Cognito login
  (brian.onieal@gmail.com) → temp IAM creds → SigV4 to the intake + console APIs.
- Submit (single + batch CSV), review dashboard, audit detail with client-side
  integrity verify, reviewer decisions (own audit record), case-document uploads.
- Verified: backend pytest 40/40, console vitest 12/12, checkov 422/0, plan
  0-drift, and a LIVE e2e (`docs/evidence/console_live_e2e.txt`).
- 15 decisions LOCKED (DEC-15: Amplify + aws4fetch auth).

## PROJECT STATE
- **Capstone (v1.0.0):** complete — all 4 graded commitments demonstrated + live.
- **Phase 2 console (v1.1.0–v1.4.0):** complete — deployed, authenticated, live.
- **Live infrastructure:** the full pipeline + console run in us-east-2.

## NEXT / OPEN
- **🏁 Phase 4 "Showcase & Demo Readiness" is COMPLETE + LIVE** (BUILD APPROVED 2026-07-04).
  - v3.0.0 Executive Showcase — DONE + LIVE.
  - v3.1.0 Demo Controls (admin-only "Clear data") — DONE + LIVE (working data zeroed).
  - v3.2.0 Console Depth (real Profile + honest Settings + OPTIONAL TOTP MFA) — DONE + LIVE.
- The locked roadmap v0.1.0 → v2.4.0 remains complete underneath. Anything further
  (v3.3.0 real SES Notifications, etc.) is a new gate — re-run BUILD APPROVED.
- **Teardown** available anytime (audit bucket stays under Object Lock).
- **Teardown** available anytime (destroy the tear-downable resources; audit
  bucket stays under Object Lock). The meter is running on live infra.

## DECISIONS SNAPSHOT
21 of 21 LOCKED.
