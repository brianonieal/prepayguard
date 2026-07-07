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

1. A payment is submitted (single via the API, in bulk by uploading a CSV, or
   automatically on a schedule by the feeder pulling real awards from USAspending).
2. The pipeline screens the payee and TIN against Do Not Pay reference sources.
3. A transparent, rule-based risk score produces one of three dispositions:
   approve, route to human review, or reject.
4. Every disposition is written to an immutable audit record (S3 Object Lock,
   COMPLIANCE mode) with a SHA-256 integrity hash.
5. Ambiguous cases land in the reviewer console for a human decision, which is
   itself audited.

## Architecture

Seven Lambda components (a five-stage screening pipeline plus two scheduled data
feeders) and a console API, all Lambda container images decoupled by SQS and
defined entirely in Terraform:

| Component | Role | Module |
|---|---|---|
| **A. Payment Intake API** | IAM-authed API Gateway, payment-ID idempotency, enqueue | `modules/api_intake_stage` |
| **B. Enrichment and Reference-Match** | Match payee / TIN against reference sources: exact, fuzzy, and Bedrock-embedding **semantic** | `modules/queue_worker_stage` (shared) |
| **C. Risk-Scoring and Decision Engine** | Score risk, decide approve / review / reject | `modules/queue_worker_stage` (shared) |
| **D. Disposition Router and Audit Logger** | Immutable audit write, route ambiguous cases to review, webhook notify | `modules/queue_worker_stage` (shared) |
| **E. Batch Ingest** | S3-triggered bulk **CSV / Excel / JSON** intake, reuses A's idempotency store and queue | `modules/batch_ingest_stage` |
| **F. Feeder** | Scheduled (EventBridge, business-hours ET) pull of real awards from the public USAspending API, dropped to Component E for screening | `modules/scheduled_feeder` |
| **G. Refresher** | Scheduled (EventBridge, daily) re-pull of the real SAM.gov exclusions, re-embed, and republish of the versioned reference list when it changed | `modules/scheduled_refresher` |
| **Console API** | Read/action router: reviews, audit, decisions, batches, reference data, feed config, LLM briefs, analytics | `modules/console_api` |

Components F and G make the data flow automatic: F feeds real federal payments in
on a schedule (no manual upload) by dropping a file for Component E, and G keeps
the Do Not Pay watchlist current on its own. Both use keyless public sources,
degrade gracefully on a source error (skip the run, never crash the schedule), and
have an `enabled` stop switch.

Supporting modules: `audit_store` (S3 Object Lock, COMPLIANCE mode),
`review_queue` (human-review path), `console_foundation` (Cognito, S3 and
CloudFront hosting, reviews table), `reference_store` (versioned screening lists),
`scheduled_feeder` / `scheduled_refresher` (the F/G schedules and least-privilege
roles), `ecr_repo` (per-component registries, 8x).

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system overview, failure
modes, rollback mechanism, and known unknowns. All 27 architectural decisions are
locked in [foundation/DECISIONS.md](foundation/DECISIONS.md).

## Screening intelligence

Every disposition is deterministic and explainable, and every one cites the exact
screening-list version it was judged against:

* **Rule-based matching** (DEC-14): TIN exact, name exact, name fuzzy.
* **Semantic matching** (Bedrock Titan embeddings): catches payee variants the
  string rules miss (for example "Globex Overseas Incorporated" against a listed
  "Globex Offshore Inc"), by cosine similarity over per-entry vectors stored in
  the versioned reference document. No vector database.
* **Versioned reference data**: admins publish new Do Not Pay lists through the
  console; each screening record cites the list version it matched. The live list
  includes the real **SAM.gov exclusions** (federal debarment) alongside three
  synthetic modeled sources; Component G re-pulls and republishes SAM daily, only
  when it changed, so the watchlist stays current on its own (DEC-22, DEC-24).
* **LLM adjudication briefs** (Bedrock Nova Lite): an on-demand, evidence-grounded
  summary for reviewers. Advisory only, never written to the immutable audit record.

## The reviewer console

A React and Vite single-page app hosted on S3 behind CloudFront. As of v3.7.0 the
console is organized into three primary surfaces (Dashboard, Review Queue, Audit
log) with admin configuration grouped under an **Admin** menu and payment submission
moved to a header button and modal:

* Cognito login to temporary IAM credentials, then browser SigV4 (aws4fetch) to
  the APIs. No static keys in the browser.
* Submit a single payment (a header button that opens a modal) or upload a batch
  file (**CSV, Excel, or JSON**), ingested server-side by Component E.
* **Dashboard**: a flagged-item hero (the count awaiting human review, with a jump
  to the queue) on top of the executive showcase, a live, narrative walkthrough of
  what the platform is, how it decides, and what it has processed, with hand-built
  charts (disposition mix, risk hit rate, match types), a pipeline diagram, the
  scoring rules in plain English, and three real worked examples (approved, flagged,
  rejected).
* **Review Queue** with server-side status filters, cursor pagination, search, and
  bulk approve / reject; audit detail with client-side integrity verification, score
  explainability, semantic-match evidence, and an optional AI brief.
* **Audit log** tab: the immutable audit log with an auditor CSV export, plus
  throughput and reviewer-productivity views (auditor and admin).
* **Admin** menu (admin only): a **reference-data** editor (publish versioned lists),
  a **Feed** builder (a USAspending-style search that configures what Component F
  pulls: award types, agency and sub-agency, location, and date range, with Save and
  Run-now), and **Demo controls**.
* Account self-service in **Profile**: change your password and enroll in
  time-based one-time-password (TOTP) two-factor, both through Cognito. MFA is
  optional and opt-in, so existing sign-ins are unchanged unless a user enables it.
* Admin-only **Demo controls** in Settings: a typed-confirmation reset that clears
  all uploaded records (review queue, audit index, batch summaries, idempotency
  store, and the uploaded batch files and case documents) for a clean demonstration.
  The immutable audit records under S3 Object Lock are never affected, so the
  console dashboards read empty while every historical disposition stays permanently
  locked in the audit bucket, verifiable directly there.
* Roles: **submitter**, **reviewer**, **admin**, and a read-only **auditor**.
  Segregation of duties is enforced: an approver cannot clear a payment they
  submitted; the auditor can view everything but decide nothing.

## Graded commitments and evidence

| # | Commitment | Evidence (test) | Gate |
|---|---|---|---|
| 1 | Idempotency via payment-ID deduplication | `tests/test_idempotency.py` | v0.2.0 |
| 2 | Component-failure routing to manual review | `tests/test_failure_routing.py` | v0.4.0 |
| 3 | Queue-depth scaling | `tests/test_queue_depth_scaling.py` | v0.5.0 |
| 4 | S3 Object Lock immutability | `tests/test_object_lock.py` | v0.4.0 |
| + | Review-notification webhook and scoped secret (DEC-7) | `tests/test_review_notification.py` | v0.4.0 |

## Status and roadmap

**Everything through v3.7.1 is complete and live.**

* **Phase 1 (v0.1.0 to v1.0.0):** the backend pipeline plus the capstone deliverable.
* **Phase 2 (v1.1.0 to v1.4.0):** the reviewer console, deployed and live.
* **Hardening:** v1.5.0 read-scale (GSI pagination, O(1) audit lookup) and v1.6.0
  write-scale (batch ingestion, bulk actions).
* **Phase 3, "Do-Not-Pay Intelligence":** v2.0.0 roles and segregation of duties,
  v2.1.0 versioned reference-data lifecycle, v2.1.2 multi-format batch ingestion,
  v2.2.0 semantic payee matching (Bedrock embeddings), v2.3.0 LLM adjudication
  briefs, v2.4.0 analytics and compliance reporting with a read-only auditor role.
* **Phase 4, "Showcase and Demo Readiness":** v3.0.0 the executive Overview tab,
  v3.1.0 admin demo-reset controls, v3.2.0 a real Profile (live identity fields,
  password change, and optional TOTP two-factor) with an honest Settings screen.
* **Phase 5, "Automated data and console restructure":** v3.3.0 the automated
  USAspending feeder (Component F) on a business-hours schedule, v3.4.0 the daily
  SAM refresher (Component G), v3.5.0 to v3.6.0 the in-console Feed builder (the
  full USAspending search surface driving what F pulls), v3.7.0 the console
  restructure into three surfaces plus an Admin menu, and v3.7.1 a Feed-page layout
  fix.

Verified per gate: `pytest` 135/135, console `vitest` 34/34, `checkov` clean, `ruff`
clean, `terraform validate` clean, and a live end-to-end run. Full history:
[foundation/VERSION_ROADMAP.md](foundation/VERSION_ROADMAP.md) and
[foundation/CHANGELOG.md](foundation/CHANGELOG.md).

## Tech stack

AWS (Lambda, SQS, S3 Object Lock, DynamoDB, API Gateway, Cognito, CloudFront,
KMS, Secrets Manager, EventBridge Scheduler, Bedrock, ECR), Terraform, Python for
the handlers, React and Vite for the console. The infrastructure is AWS-only; the
one external dependency is read-only calls to two keyless public federal data
sources, the USAspending API (Component F) and the SAM.gov exclusions mirror
(Component G), each of which degrades gracefully if the source is unavailable.

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
  scheduled_feeder/      # Component F: EventBridge feeder (USAspending)
  scheduled_refresher/   # Component G: EventBridge SAM refresher
  audit_store/           # S3 Object Lock COMPLIANCE (commitment 4)
  review_queue/          # human-review path (commitment 2)
  console_foundation/    # Cognito, S3 + CloudFront hosting, reviews table
  console_api/           # console read/action router API
  ecr_repo/              # per-component container registry (8x)
src/                     # component handlers (A through G) + console API
console/                 # React and Vite reviewer console (SPA)
tests/                   # commitment and behavior tests (see table above)
foundation/              # project contract, decisions, roadmap, memory
docs/evidence/           # captured live end-to-end proofs
ARCHITECTURE.md          # failure modes, rollback, known unknowns
```
