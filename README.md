# Treasury (PrePayGuard)

Pre-payment integrity screening pipeline modeled on the U.S. Treasury Bureau of
the Fiscal Service **Do Not Pay** program — payments are screened *before* they
go out; improper ones are flagged or blocked, and every disposition is recorded
immutably.

Capstone project, JHU Certificate in AI Engineering (CO.EN.AIE.LLL.2026.01).

## Architecture

Four Lambda container images decoupled by SQS, defined entirely in Terraform:

| Component | Role | Module |
|---|---|---|
| **A — Payment Intake API** | IAM-authed API Gateway → idempotency check → queue | `modules/api_intake_stage` |
| **B — Enrichment & Reference-Match** | Match payment data against reference sources | `modules/queue_worker_stage` (shared) |
| **C — Risk-Scoring & Decision Engine** | Score risk, decide disposition | `modules/queue_worker_stage` (shared) |
| **D — Disposition Router & Audit Logger** | Immutable audit write, route ambiguous → human review, webhook notify | `modules/queue_worker_stage` (shared) |

Supporting modules: `audit_store` (S3 Object Lock, COMPLIANCE mode),
`review_queue` (human-review path), `ecr_repo` (per-component registries, 4×).

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system overview, failure
modes, rollback mechanism, and known unknowns. All 12 architectural decisions
are locked in [foundation/DECISIONS.md](foundation/DECISIONS.md).

## Graded commitments → evidence

| # | Commitment | Evidence (test) | Gate |
|---|---|---|---|
| 1 | Idempotency via payment-ID deduplication | `tests/test_idempotency.py` | v0.2.0 |
| 2 | Component-failure routing to manual review | `tests/test_failure_routing.py` | v0.4.0 |
| 3 | Queue-depth scaling | `tests/test_queue_depth_scaling.py` | v0.5.0 |
| 4 | S3 Object Lock immutability | `tests/test_object_lock.py` | v0.4.0 |
| — | Review-notification webhook + scoped secret (DEC-7) | `tests/test_review_notification.py` | v0.4.0 |

## Working with the Terraform

```sh
cd environments/dev
terraform init
terraform fmt -check -recursive ../..
terraform validate
terraform plan        # requires AWS credentials
```

`terraform apply` is always a **manual, deliberate action** (DEC-6 — CI is
plan-only, no auto-apply). Local tooling (terraform, tflint) lives in `.tools/`
(gitignored); static analysis is `tflint` + `checkov` at the repo root.

⚠️ **Before touching `audit_retention_days`**: read the irreversibility block
in `environments/dev/terraform.tfvars`. Object Lock COMPLIANCE retention cannot
be shortened on written objects by anyone, ever (DEC-4).

## Repo layout

```
environments/dev/        # instantiates all modules, wires the queue chain
modules/
  queue_worker_stage/    # SHARED (DEC-1): used 3x via for_each (B, C, D)
  api_intake_stage/      # Component A: API GW (AWS_IAM) + Lambda + out-queue
  audit_store/           # S3 Object Lock COMPLIANCE (commitment 4)
  ecr_repo/              # per-component container registry (4x)
  review_queue/          # human-review path (commitment 2)
src/                     # component handlers (land at v0.2.0–v0.4.0)
tests/                   # commitment evidence tests (see table above)
foundation/              # project contract, decisions, roadmap, memory
ARCHITECTURE.md          # failure modes, rollback, known unknowns
```

## Status

Gate **v0.1.0 — Terraform Foundation & Shared Module** (infrastructure shape;
no application logic yet). Roadmap: [foundation/VERSION_ROADMAP.md](foundation/VERSION_ROADMAP.md).
