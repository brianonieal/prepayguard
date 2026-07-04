# PrePayGuard (Treasury)

Pre-payment integrity screening pipeline modeled on the U.S. Treasury Bureau of
the Fiscal Service **Do Not Pay** program. Payments are screened *before* they go
out; improper ones are flagged or blocked, and every disposition is recorded
immutably. A reviewer console sits on top for human adjudication.

Capstone project, JHU Certificate in AI Engineering (CO.EN.AIE.LLL.2026.01).

## Live deployment

**https://d2rbxaf6pqgvb1.cloudfront.net**

The full pipeline and console run live in AWS (us-east-2). The console is a real,
signed-in application: Cognito login gives you temporary IAM credentials, and the
browser SigV4-signs every API call (the same AWS_IAM model the backend enforces).

Access is provisioned, there is no public sign-up (operator-managed users only, by
design). A visitor sees the login screen; a walkthrough of the working end-to-end
flow (login, submit, flag, review, decide) is captured under `docs/evidence/`.

## What it does

1. A payment is submitted (single via the API, or in bulk by uploading a CSV).
2. The pipeline screens the payee and TIN against Do Not Pay reference sources.
3. A transparent, rule-based risk score produces one of three dispositions:
   approve, route to human review, or reject.
4. Every disposition is written to an immutable audit record (S3 Object Lock,
   COMPLIANCE mode) with a SHA-256 integrity hash.
5. Ambiguous cases land in the reviewer console for a human decision, which is
   itself audited.

## Architecture

Five pipeline components plus a console API, all Lambda container images
decoupled by SQS and defined entirely in Terraform:

| Component | Role | Module |
|---|---|---|
| **A. Payment Intake API** | IAM-authed API Gateway, payment-ID idempotency, enqueue | `modules/api_intake_stage` |
| **B. Enrichment and Reference-Match** | Match payee / TIN against reference sources | `modules/queue_worker_stage` (shared) |
| **C. Risk-Scoring and Decision Engine** | Score risk, decide approve / review / reject | `modules/queue_worker_stage` (shared) |
| **D. Disposition Router and Audit Logger** | Immutable audit write, route ambiguous cases to review, webhook notify | `modules/queue_worker_stage` (shared) |
| **E. Batch Ingest** | S3-triggered bulk CSV intake, reuses A's idempotency store and queue | `modules/batch_ingest_stage` |
| **Console API** | Read/action router for the console: list reviews, fetch audit, decisions, batches | `modules/console_api` |

Supporting modules: `audit_store` (S3 Object Lock, COMPLIANCE mode),
`review_queue` (human-review path), `console_foundation` (Cognito, S3 and
CloudFront hosting, reviews table), `ecr_repo` (per-component registries, 6x).

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system overview, failure
modes, rollback mechanism, and known unknowns. All 17 architectural decisions are
locked in [foundation/DECISIONS.md](foundation/DECISIONS.md).

## The reviewer console

A React and Vite single-page app hosted on S3 behind CloudFront:

* Cognito login to temporary IAM credentials, then browser SigV4 (aws4fetch) to
  the APIs. No static keys in the browser.
* Submit a single payment or upload a CSV batch (ingested server-side by
  Component E).
* Review queue with server-side status filters, cursor pagination, and search.
* Audit detail with client-side integrity verification and score explainability.
* Case-document attachments (presigned S3 uploads) and bulk approve / reject.
* Roles: **submitter**, **reviewer**, **admin**. Segregation of duties is
  enforced: an approver cannot clear a payment they submitted.

## Graded commitments and evidence

| # | Commitment | Evidence (test) | Gate |
|---|---|---|---|
| 1 | Idempotency via payment-ID deduplication | `tests/test_idempotency.py` | v0.2.0 |
| 2 | Component-failure routing to manual review | `tests/test_failure_routing.py` | v0.4.0 |
| 3 | Queue-depth scaling | `tests/test_queue_depth_scaling.py` | v0.5.0 |
| 4 | S3 Object Lock immutability | `tests/test_object_lock.py` | v0.4.0 |
| + | Review-notification webhook and scoped secret (DEC-7) | `tests/test_review_notification.py` | v0.4.0 |

## Status and roadmap

Live through **v2.0.0**. Delivered so far:

* **Phase 1 (v0.1.0 to v1.0.0):** the backend pipeline plus the capstone
  deliverable. Done.
* **Phase 2 (v1.1.0 to v1.4.0):** the reviewer console, deployed and live. Done.
* **Hardening:** v1.5.0 read-scale (GSI pagination, O(1) audit lookup) and
  v1.6.0 write-scale (batch ingestion, bulk actions). Done.
* **Phase 3, "Do-Not-Pay Intelligence":** v2.0.0 roles and segregation of duties
  is done and live; v2.1.0 to v2.4.0 are planned (reference-data lifecycle,
  semantic payee matching with Bedrock embeddings, LLM adjudication briefs,
  analytics and compliance reporting).

Verified at the current gate: `pytest` 60/60, console `vitest` 15/15, `checkov`
clean, `terraform plan` shows no drift. Full plan:
[foundation/VERSION_ROADMAP.md](foundation/VERSION_ROADMAP.md).

## Tech stack

AWS (Lambda, SQS, S3 Object Lock, DynamoDB, API Gateway, Cognito, CloudFront,
KMS, Secrets Manager, ECR), Terraform, Python for the handlers, React and Vite
for the console. No non-AWS services.

## Working with the Terraform

```sh
cd environments/dev
terraform init
terraform fmt -check -recursive ../..
terraform validate
terraform plan        # requires AWS credentials
```

`terraform apply` is always a manual, deliberate action (DEC-6, CI is plan-only
with no auto-apply). Local tooling (terraform, tflint) lives in `.tools/`
(gitignored); static analysis is `tflint` plus `checkov` at the repo root.

Warning: before touching `audit_retention_days`, read the irreversibility block
in `environments/dev/terraform.tfvars`. Object Lock COMPLIANCE retention cannot
be shortened on written objects by anyone, ever (DEC-4).

## Repo layout

```
environments/dev/        # instantiates all modules, wires the queue chain
modules/
  queue_worker_stage/    # SHARED (DEC-1): used 3x via for_each (B, C, D)
  api_intake_stage/      # Component A: API GW (AWS_IAM) + Lambda + out-queue
  batch_ingest_stage/    # Component E: S3-triggered bulk CSV ingest
  audit_store/           # S3 Object Lock COMPLIANCE (commitment 4)
  review_queue/          # human-review path (commitment 2)
  console_foundation/    # Cognito, S3 + CloudFront hosting, reviews table
  console_api/           # console read/action router API
  ecr_repo/              # per-component container registry (6x)
src/                     # component handlers (A through E) + console API
console/                 # React and Vite reviewer console (SPA)
tests/                   # commitment and behavior tests (see table above)
foundation/              # project contract, decisions, roadmap, memory
docs/evidence/           # captured live end-to-end proofs
ARCHITECTURE.md          # failure modes, rollback, known unknowns
```
