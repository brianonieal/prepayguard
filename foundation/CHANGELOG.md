# CHANGELOG.md — PrePayGuard ("Treasury")

## v2.1.1 — Hotfix: browser CORS preflight (2026-07-04)

**Every browser API call was failing.** The unsigned CORS preflight (`OPTIONS`) was denied by both APIs' resource policies (403, no `Access-Control-Allow-Origin`), so no `fetch` from the SPA ever completed. Latent since the resource policies were introduced (v1.2.0/v1.4.0) and undetected across six console gates because all live e2e used SigV4/boto3, which does not send a CORS preflight. Surfaced when the owner clicked "Submit 24 payments" in a real browser.

- Both API resource policies now explicitly **Allow the anonymous OPTIONS preflight** (`*/OPTIONS/*`, any principal — OPTIONS is a MOCK returning only CORS headers, no data path). Intake's catch-all Deny also now exempts `aws:PrincipalType = Anonymous` (the console's already did).
- New **`scripts/check_cors.py`** deploy guard: probes the real OPTIONS preflight on every route and fails if ACAO is missing — the exact gap SigV4 tests cannot cover.
- Infra-only (no Lambda/image/SPA change). Verified live: all 8 preflights 200 + correct ACAO; signed `POST /batches` returns 200 + ACAO + batch_id (the full browser path).


## v2.1.0 — Reference-Data Lifecycle (2026-07-04, Phase 3)

**The screening lists are now managed and versioned — every screening decision cites the exact list version it matched against.**

### Backend
- New **`reference_store`** module: private versioned S3 bucket holding `reference/current.json` (active) + immutable `reference/versions/{N}.json` history. Terraform owns the bucket, never the documents; v1 seeded from the bundled list by `scripts/seed_reference_data.py` (idempotent).
- **Component B** fetches the list from the store (60s warm-cache TTL) and stamps **`reference_version`** on the enrichment block. Failure posture: warm cache on S3 error, else raise → retry/DLQ (never screen blind). Bundled JSON remains only as the seed source / no-store test fallback.
- **Component D** writes **`provenance.reference_list_version`** into every immutable audit record — the citation.
- **console_api:** `GET /reference`, `PUT /reference` (**admin-only**: edge Deny on the reviewer role + `ADMIN_ROLE_NAME` handler check; entry validation; `If-None-Match` conditional put claims the next version so concurrent publishes can't collide), `GET /reference/versions[/{n}]`. CORS gains PUT.
- All 6 images rebuilt **v2.1.0** (D `COMPONENT_VERSION` 2.1.0).

### Frontend (deployed)
- Admin-only **Reference Data** screen: active-version stats, editable entries table (add/remove/edit, severity select), **Publish new version**, version history with view. **AuditDetail** shows "reference list vN (list version screened against)".
- Second demo account **brian.onieal+reviewer@gmail.com** (reviewer group) provisioned with the owner's explicit approval — also enables the cross-account SoD approve path for manual testing.

### Verified
- `pytest` 69/69 · `vitest` 18/18 · checkov 0 failed (**coverage re-verified**: 133 resources scanned, 0 parse errors — the passed-count drop vs v2.0.0 is checkov module-attribution dedup after init, not lost coverage) · `tflint` clean · `plan` 0-drift.
- **LIVE PASS**: seeded v1 (8 entries) → admin published v2 (+1 entry) → payment matching the **v2-only** entry flagged to review → **audit record cites `reference_list_version: 2`** → reviewer `PUT /reference` 403 (normal reviewer access intact) → v1 history still resolvable with its original 8 entries.

**DEC-18 LOCKED** — versioned S3 document store, admin-only publish, seeded out-of-band.

## v2.0.0 — Roles & Segregation of Duties (2026-07-04, Phase 3)

**The console now separates who may submit from who may approve — and an approver can't clear a payment they submitted.**

### Backend
- **Cognito groups → per-group IAM roles** (submitter / reviewer / admin) via Identity-Pool **Token role-mapping** (`cognito:preferred_role`); a user in no group falls back to a no-access role.
- **Edge authorization (resource policies):** reviewer+admin → every route; **submitter → only the batch-upload routes**; all three may submit (intake admits all three + the machine payment-submitter role).
- **Segregation of duties (app-level, the part IAM can't express):** Component A stamps `submitted_by` (`cognitoIdentityId`), B/C pass it through, Component D writes it to the reviews table, and console_api's `_apply_decision` returns **403** when decider == submitter — on **single and bulk** decisions.
- All 6 images rebuilt **v2.0.0**.

### Frontend (deployed)
- Role read from the ID token's `cognito:groups` → nav + actions gate by role (submitter sees Submit only; reviewer/admin get the queue + decisions); a route guard bounces a submitter off `/reviews`; role chip in the topbar; Profile shows the real role.

### Verified
- `pytest` 60/60 · `vitest` 15/15 · `checkov` 502/0 · `tflint` clean · `plan` 0-drift.
- **LIVE**: `brian` assumed the **admin** role via Token role-mapping; **self-approve → 403 `segregation_of_duties`**; a *different* submitter's payment → **200**.
- Known IAM-propagation error on the two resource policies (roles created in the same apply) → re-applied clean once the roles propagated.

**DEC-17 LOCKED** — role model + segregation of duties.

## v1.6.0 — Write-Scale Hardening (2026-07-04, Phase 2)

**Batch CSV files ingest server-side through a new pipeline component; reviewers clear many cases in one action.**

### Backend
- **Component E — Batch Ingest** (new S3-triggered Lambda, `src/component_e_batch_ingest`). A CSV uploaded to the `batch-imports` bucket fires an `ObjectCreated` event; E parses each row and performs the **same** payment-ID idempotency claim + enqueue as Component A, against the **same** idempotency table and intake queue (**DEC-16**) — so single-API and batch submissions dedupe against each other. Batched via `SendMessageBatch`; intra-file duplicates deduped too. Writes a per-file **batch summary** (counts + row errors).
- `console_api`: `POST /batches` (presign CSV upload + mint `batch_id`), `GET /batches/{id}` (poll summary; "processing" until E writes), `GET /batches`. **`POST /reviews/decisions`** — one decision applied to ≤50 payments, **each still writing its own immutable audit record**; partial-success reported. `_decide` refactored to a shared `_apply_decision` core.
- New `modules/batch_ingest_stage`: batch-imports S3 bucket (SSE, versioned, CORS, lifecycle) + `batches` table + Component E Lambda + least-priv IAM + S3→Lambda trigger (to the `live` alias, DEC-10). All 6 images rebuilt (**v1.6.1**), deployed.

### Frontend (deployed)
- **Submit:** batch upload is now server-side — presign → upload the raw CSV once → poll the summary (queued / duplicate / rejected + errors), replacing the per-row client loop. Client-side parse kept for the preview/validation table.
- **Review queue:** row checkboxes + a bulk action bar ("Approve N / Reject N") over the loaded page.

### Verified
- Backend `pytest` 56/56 · console `vitest` 13/13 · `checkov` 472/0 · `tflint` clean · `plan` 0-drift.
- **LIVE**: presign → `aws s3` upload → E summary **queued 2 / duplicate 1** (intra-file dedup proven on a file with a repeated id) → **bulk approve** flipped the pending payment to approved.
- Caught + fixed an intra-file duplicate bug pre-deploy (first occurrence still PENDING when the repeat is checked → added an in-file `seen` set).

## v1.5.0 — Read-Scale Hardening (2026-07-04, Phase 2)

**Reviews list and audit lookup now scale: GSI-backed pagination + an O(1) audit index.**

### Backend
- `reviews` table: new GSI `status-received_at-index`. `GET /reviews` **queries by status** (paginated, newest-first) instead of a full-table Scan — `?status=&limit=&cursor=`, returns `next_cursor` (base64 `LastEvaluatedKey`). No-status requests still Scan.
- New `audit_index` table (`payment_id`→`audit_key`). Component D **v1.5.0** writes it for **every** disposition, so `GET /audit/{id}` is a GetItem→GetObject (**O(1)**); a `payment_id`-prefix Scan fallback keeps pre-index records resolvable.
- IAM/env wiring: D gains `dynamodb:PutItem` on the index; `console_api` gains `dynamodb:Query` on the GSI + `GetItem` on the index. All 5 images rebuilt (v1.5.0), deployed (alias repoints, DEC-10).

### Frontend (deployed)
- Review queue: **server-side status filter** (chips refetch page 1) + **"Load more"** cursor paginator; search stays client-side over the loaded page.

### Verified
- Backend `pytest` 43/43 · console `vitest` 12/12 · `checkov` 423/0 · `plan` 0-drift.
- **LIVE**: e2e still PASS (submit→review→decide, audit via index); paginated `GET /reviews?status=pending&limit=1` returns a page + `next_cursor`.

### Deferred → v1.6.0 (Write-Scale)
- S3 batch-file ingestion (S3-triggered Lambda) + bulk review actions (batch decision endpoint + multi-select UI).

## v1.4.0 — Treasury Console GA (2026-07-04, Phase 2)

**The console is LIVE: real Cognito login, live data, deployed to CloudFront, end-to-end verified.**

### Backend
- `console_api`: attachment endpoints (`POST`/`GET /reviews/{id}/attachments`, presigned S3 PUT) + private uploads bucket (CORS, SSE, versioned, lifecycle).
- Intake API: CORS preflight (OPTIONS) + `Access-Control-Allow-Origin` response header so the browser can submit.
- Component D **v1.4.1**: reviews table now stores `payee` + `match` summary for the queue columns. All 5 images rebuilt (v1.4.1), deployed (alias repoints, DEC-10).

### Frontend (wired + deployed)
- **aws-amplify** (Cognito User Pool → Identity Pool temp creds) + **aws4fetch** SigV4 (**DEC-15**). Fake data swapped for signed calls; loading/error/empty states.
- Deployed SPA to S3 + CloudFront (`scripts/deploy-console.sh`). Fixed a real drift bug: Terraform managed `index.html` and reverted the SPA — removed from state; Terraform owns the bucket, the deploy owns its contents.

### Verified
- Backend `pytest` 40/40 · console `vitest` 12/12 · `checkov` 422/0 · `tflint` clean · `plan` 0-drift.
- **LIVE e2e** (`docs/evidence/console_live_e2e.txt`): Cognito login → temp creds → SigV4 submit → review → decision → status flip, all 200.
- **Live: https://d2rbxaf6pqgvb1.cloudfront.net** (user `brian.onieal@gmail.com`).

## v1.3.0 — Treasury Console UI (2026-07-03, Phase 2)

Static React/Vite SPA (4 screens) reviewed live as the mockup+frontend artifact. Batch CSV upload, review dashboard with stat cards, audit detail, profile/settings/user-menu. **Tier-1 folded in:** client-side SHA-256 integrity verify (verify→tamper→fail), hash routing + deep links, search/filters, score explainability. Polish: footer, full-height shell, density toggle. vitest 15/15, build clean; console job added to `ci.yml`. Static (fake data).

## v1.2.0 — Console Read/Action API (2026-07-03, Phase 2)

One router Lambda behind an IAM-authed REST API (console role only, CORS preflight): `GET /reviews`, `GET /audit/{payment_id}`, `POST /reviews/{id}/decision`. Reviewer decisions write their own integrity-hashed audit record to Object Lock. pytest 37/37, checkov 410/0; deployed + prod smoke 200s.

## v1.1.0 — Treasury Console Foundation (2026-07-03, Phase 2)

**Everything the console UI stands on, deployed live.**

### Added
- `modules/console_foundation/` — Cognito User Pool (admin-create-only, strong password policy) + SPA client + Identity Pool → **authenticated IAM role** (temp creds → SigV4, reusing the DEC-5 mechanism for humans); private S3 site bucket + CloudFront (OAC, explicit security-headers policy, US-only geo, HTTPS); `treasury-dev-reviews` DynamoDB table (queryable dashboard view; SQS stays the durable hand-off).
- Component D v1.1.0: writes each review item to the reviews table (audit → queue → **table** → webhook); conditional `dynamodb:PutItem` via the shared module's DEC-1 pattern; +2 tests.
- `api_intake_stage`: resource policy now takes a **list** of allowed roles (submitter + console authenticated) — same DEC-5 deny-all-but-named mechanism, one more named principal. Console invoke policy attached at env level (breaks the module cycle, PAT-T1 class).

### Deployed
- Full apply (17 add / 11 change / 1 destroy after image bump). **DEC-10 exercised for real:** all 4 images rebuilt as `v1.1.0`, new Lambda versions published, `live` aliases repointed (disposition → version 2). One IAM-propagation retry on the API policy (known first-deploy class).
- Console shell live: https://d2rbxaf6pqgvb1.cloudfront.net (placeholder until v1.3.0).

### Verified
- pytest **31/31** · checkov **265/0** (3 console fixes: security-headers policy w/ HSTS preload, site lifecycle, US geo whitelist; 8 justified skips) · ruff/tflint clean.
- **Live smoke:** `console-smoke-1` (name match, score 48 → review) landed in the reviews table with `status=pending` via the redeployed Component D.


## v1.0.0 — Capstone Deliverable (2026-07-03)

**Full live deployment + end-to-end run + DEC-11 handoff package. Project complete.**

### Deployed (real AWS, us-east-2)
- Built + pushed 4 Lambda container images (Docker v2 schema-2 manifest) and ran a full `terraform apply` (~68 resources). Fixed two issues only a real deploy surfaces: the buildx **OCI manifest** (Lambda rejects it → rebuilt with `oci-mediatypes=false`), and the account-level **API Gateway CloudWatch Logs role** required to enable stage access logging.

### Live end-to-end run
- Three SigV4-signed payments through the deployed API: **approve** / **reject** (TIN→DMF match) / **review** (name→sam_exclusions), plus a duplicate that returned an **idempotent replay**. Audit records landed in S3 Object Lock, the review item in the review queue, the webhook POST captured. **All four graded commitments demonstrated live.** Evidence: `docs/evidence/`.

### Added
- `docs/HANDOFF.md` + `docs/HANDOFF.docx` — the DEC-11 six-section handoff package (architecture, tests, deployment, security findings + risk table + scan appendix, residual risks, follow-on).
- `scripts/send_payment.py` (SigV4 intake client), `scripts/live_object_lock_proof.py`.

### Verified
- `pytest` 29/29 · `checkov` 289/0 · ruff/pip-audit/tflint clean · CI green on Actions.

### Status
**v1.0.0 — capstone complete.** 14 decisions locked; all four commitments demonstrated by both automated tests and a live run. Deployed and running in us-east-2.

## v0.6.0 — CI/CD & Security Scanning (2026-07-03)

**GitHub Actions live and GREEN. DEC-6/8/9/10 satisfied. Repo published (private).**

### Added
- `.github/workflows/ci.yml` — push/PR: `fmt`/`validate`/`tflint` + `pytest` + **ruff** + **pip-audit** + **checkov** (no AWS creds — static + hermetic).
- `.github/workflows/plan.yml` — `terraform plan` on PRs to main, posts diff as a comment, **no auto-apply** (DEC-6). Requires GH secret `AWS_PLAN_ROLE_ARN` (documented in-file).
- `ruff.toml` (DEC-9); `docs/ROLLBACK.md` runbook (DEC-10 — versions + aliases). Grype wired conceptually, gated on the image build.

### Verified (locally + on GitHub Actions)
- Repo **github.com/brianonieal/prepayguard** (private). **CI run green** — terraform job (fmt/init/validate/tflint) ✓ and python job (ruff/pip-audit/pytest 29/29/checkov) ✓.
- ruff + pip-audit clean across all four component runtimes.

### Notes
- Node20-deprecation annotation (actions forced to Node24) — cosmetic; bump action majors as follow-up.
- `plan.yml` awaits the `AWS_PLAN_ROLE_ARN` OIDC secret; `ci.yml` needs no secrets.

## v0.5.0 — Queue-Depth Scaling & DLQ Hardening (2026-07-03)

**Commitment 3 demonstrated — ALL FOUR graded commitments now complete. Config/plan-based evidence; live load demo deferred to the full-deploy milestone.**

### Added
- `tests/test_queue_depth_scaling.py` (3) — parses `terraform show -json` and asserts, per worker stage: event-source-mapping `scaling_config.maximum_concurrency` (≥2), `ReportBatchItemFailures`, `batch_size`, the queue-depth CloudWatch alarms, and DLQ redrive wiring. Skip-guarded so hermetic (no-terraform/no-creds) runs don't fail.

### Verified
- `pytest` **29/29**. tflint/checkov unchanged (271/0, no `.tf` change); `plan` 68/0/0.

### Status
- **4 / 4 graded commitments demonstrated** (1 idempotency, 2 failure-routing, 3 scaling, 4 immutability — #4 live-verified). The scaling mechanism was built at v0.1.0; this gate proves it. DLQ/redrive already hardened (14-day DLQ retention, `maxReceiveCount` 3, redrive-allow scoping).

## v0.4.0 — Component D: Disposition, Audit, Notify (2026-07-03)

**Commitments 2 & 4 demonstrated + DEC-7. Live Object-Lock immutability proven against real AWS.**

### Added
- `src/component_d_disposition/` — SQS-triggered handler: writes a **compliance audit record** (decision + evidence + provenance + SHA-256 integrity hash) to the S3 Object Lock bucket (**commitment 4**, audit-first ordering); routes `review` dispositions to the human-review queue (**commitment 2**); posts a webhook (**DEC-7**) whose URL is read from Secrets Manager (stdlib `urllib`, no dep). Dockerfile + reqs.
- `tests/test_object_lock.py` (4), `tests/test_failure_routing.py` (4), `tests/test_review_notification.py` (4); conftest `disposition` fixture (moto S3 Object Lock + review SQS + secret). Message schema now complete: `payment → +enrichment → +risk → audit record`.
- `scripts/live_object_lock_proof.py` + `docs/evidence/live_object_lock_proof.txt`.

### Verified
- `pytest` 26/26.
- **LIVE commitment-4 proof** (`treasury-dev-audit-<ACCOUNT_ID>`): retention auto-applied COMPLIANCE; `delete` → AccessDenied; shorten-retention → AccessDenied.
- fmt/validate clean; tflint/checkov unchanged (271/0, no `.tf` change); `plan` 68/0/0 (audit_store live, **0 drift**).

### Deployed (first real AWS spend)
- `module.audit_store` applied (9 resources: S3 Object Lock bucket + CMK + policies). Persists — the locked proof object self-expires ~2026-07-04; the CMK is ~$1/mo.

### Notes
- moto doesn't emulate S3 default-retention auto-apply on objects (`get_object_retention` 500s); the moto test asserts bucket Object-Lock config, the live proof covers actual enforcement.

## v0.3.0 — Components B & C: Enrichment + Risk Scoring (2026-07-03)

**Pipeline middle comes alive: reference-match enrichment + risk scoring → three-way disposition. Code + tests; no Terraform change (module instances already existed), plan stays 77/0/0.**

### Added
- `src/component_b_enrichment/` — SQS-triggered handler: matches payee against a **bundled synthetic reference list** (`reference_data.json`, modeling SSA DMF / SAM exclusions / Treasury Offset / OIG LEIE) via deterministic TIN + exact/fuzzy name matching (DEC-14); attaches an `enrichment` block; forwards to Component C. Dockerfile + requirements.
- `src/component_c_risk_scoring/` — SQS-triggered handler: rule-based score → three-way disposition (**TIN → reject, name → review, none → approve**); attaches a `risk` block; forwards to Component D. Dockerfile + requirements.
- `tests/test_enrichment.py` (4) + `tests/test_risk_scoring.py` (4); conftest refactored to load three sibling `app.py` modules by path (no import collision). Message schema now: `payment → +enrichment → +risk`.

### Decisions
- **DEC-14** — screening domain model: bundled synthetic list (apply-free this gate), deterministic+fuzzy matching, transparent rule-based score; name matches route to human review (the *potential-match* case that feeds commitment 2).

### Verified
- `pytest` 14/14 · `fmt`/`validate`/`tflint` clean · `checkov` 271/0 · `terraform plan` 77/0/0 (unchanged — no `.tf` this gate).

### Known / deferred
- Domain-fidelity cross-check workflow stopped early for token efficiency; design stands on best-judgment DNP fidelity.
- ARCHITECTURE.md message-schema/failure-mode consolidation folded into v0.4.0 (when Component D consumes the full message).

## v0.2.0 — Component A: Payment Intake API + Idempotency (2026-07-03)

**Commitment 1 (idempotency) demonstrated by a passing test. Code + infra-plan + unit tests; no live apply this gate.**

### Added
- `src/component_a_intake/` — intake handler (`app.py`): DynamoDB atomic conditional write with a PENDING→SENT state machine and original-result replay (DEC-13); validates the payment body; enqueues first-seen payments to the A→B queue. `Dockerfile` (Lambda `python:3.12` base) + `requirements.txt` (boto3; no powertools — mechanism hand-rolled and visible).
- `modules/api_intake_stage`: DynamoDB idempotency table (`payment_id` PK, provisioned 5/5, TTL, PITR, SSE), least-privilege IAM (`PutItem`/`GetItem`/`UpdateItem` on that table only), `OUTPUT_QUEUE_URL` + `IDEMPOTENCY_TABLE` env wiring, and API Gateway request validation (JSON-schema model + validator) — **closes the deferred CKV2_AWS_53**.
- `tests/test_idempotency.py` (6 cases) + moto fixtures: first-seen enqueue, duplicate-replays-original-result, distinct-both-queued, conditional-write-refuses-duplicate (atomicity), crash-before-enqueue-recovered (silent-loss window), missing-`payment_id`-rejected.
- `.gitattributes` (LF normalization), `requirements-dev.txt`, `pytest.ini`.

### Decisions
- **DEC-13** — idempotency backing store: hand-rolled DynamoDB conditional write + status field, chosen over Powertools for visible-mechanism grading evidence (critical-thinker pressure-test; two HIGH objections — reject-vs-replay and two-phase silent loss — resolved in the design).

### Verified
- `pytest` 6/6 · `fmt`/`validate`/`tflint` clean · `checkov` 271/0 · `terraform plan` (us-east-2): **77 to add, 0 to change, 0 to destroy**.

### Known / deferred
- Real image build+push to ECR and first `terraform apply` deferred to when the live-AWS commitments (2, 3) need standing infrastructure.
- Live-concurrency verification of the conditional write deferred to the first live-AWS gate (atomicity asserted deterministically via moto).

## v0.1.0 — Terraform Foundation & Shared Module (2026-07-03)

**Infrastructure shape complete; no application logic (by design).**

### Added
- `modules/queue_worker_stage/` — the shared worker module (DEC-1), built first
  as the dependency root: container-image Lambda (x86_64, versioned + `live`
  alias per DEC-10), SQS event source mapping with `scaling_config.maximum_concurrency`
  (commitment 3 lever), DLQ + redrive on the input queue (commitment 2),
  scoped IAM (conditional Secrets Manager statement per DEC-7, conditional
  audit-bucket S3+KMS statements for commitment 4), queue-depth + DLQ alarms,
  X-Ray tracing, 365-day log retention.
- `modules/api_intake_stage/` — Component A: REST API Gateway with AWS_IAM auth
  + resource policy allowing exactly one role and denying all others (DEC-5),
  Lambda proxy via the `live` alias, A→B output queue, access logging.
- `modules/audit_store/` — S3 Object Lock at creation, COMPLIANCE default
  retention (no-default variable: choosing it is an explicit act), versioning,
  SSE-KMS with rotating CMK + explicit key policy, public access fully blocked,
  TLS-only + lock-mode-floor bucket policy, lifecycle hygiene rules.
- `modules/ecr_repo/` — immutable tags, scan-on-push, KMS encryption, keep-10
  lifecycle (instantiated 4×).
- `modules/review_queue/` — human-drain review queue + DLQ + oldest-item-age
  alarm (DEC-7 webhook-failure fallback).
- `environments/dev/` — full pipeline wiring: A→B→C→D queue chain, B/C/D via
  `for_each` over the shared module, payment-submitter role (DEC-5), webhook
  secret shell (DEC-7 — value never in Terraform), local backend (documented).
- Foundation: DECISIONS.md (12 LOCKED, verbatim), ARCHITECTURE.md (failure
  modes, irreversibility register, known unknowns, rollback), `.tflint.hcl`,
  `.checkov.yaml` (every skip justified), README, .gitignore.

### Verified
- `terraform fmt -check`, `terraform validate`: clean (aws provider v5.100.0 pinned).
- `tflint --recursive` (ruleset-aws 0.48.0): 0 issues.
- `checkov`: 270 passed / 0 failed; all Object Lock, versioning, encryption,
  and public-access checks pass (DEC-9's target class).
- `terraform plan` (us-east-2, account <ACCOUNT_ID>): **74 to add, 0 to change,
  0 to destroy**, no errors/warnings. Caller identity, audit bucket
  (`treasury-dev-audit-<ACCOUNT_ID>`), and Object Lock COMPLIANCE all resolved.

### Changed
- Region aligned **us-east-1 → us-east-2** (tfvars, variable default,
  ARCHITECTURE assumptions) to match the operator's account/console before the
  first plan.

### Fixed during verification (checkov triage)
- API resource policy: wildcard-principal Allow tightened to the submitter role
  (CKV_AWS_283); `create_before_destroy` on the REST API (CKV_AWS_237).
- Audit CMK: explicit key policy (CKV2_AWS_64); bucket lifecycle rules (CKV2_AWS_61).
- **Latent v0.4.0 runtime bug caught:** Component D's role lacked
  `kms:GenerateDataKey`/`kms:Decrypt` on the audit CMK — SSE-KMS audit writes
  would have failed at first invoke. Conditional KMS statement added to the
  shared module.

### Known / deferred
- Recorded for v0.2.0: `aws_ecr_image` exports the digest as `id` (NOT
  `image_digest`); prefer `code_sha256` as the image-update trigger.
  Request-validator (CKV2_AWS_53) lands with the payment schema at v0.2.0.
