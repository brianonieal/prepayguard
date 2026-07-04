# SPEC.md
# Current-gate detail.

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
- **v1.6.0 — Write-Scale Hardening (next):** S3 batch-file ingestion (presigned
  upload → S3-triggered Lambda → idempotent enqueue + batch summary, replacing the
  client-side loop); bulk review actions (batch decision endpoint + multi-select UI).
- **Teardown** available anytime (destroy the tear-downable resources; audit
  bucket stays under Object Lock). The meter is running on live infra.

## DECISIONS SNAPSHOT
15 of 15 LOCKED.
