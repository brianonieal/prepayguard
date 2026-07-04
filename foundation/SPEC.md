# SPEC.md
# Current-gate detail.

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
- **Phase 3 in progress (gate 1/5 done).** Next: **v2.1.0 — Reference-Data
  Lifecycle** (screening lists → managed, versioned store; admin-gated update path;
  each screening cites the list version it matched). Then v2.2.0 semantic matching,
  v2.3.0 LLM briefs, v2.4.0 analytics.
- **Teardown** available anytime (destroy the tear-downable resources; audit
  bucket stays under Object Lock). The meter is running on live infra.

## DECISIONS SNAPSHOT
17 of 17 LOCKED.
