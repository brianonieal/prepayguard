# SPEC.md
# Current-gate detail. Updated each gate.

## CURRENT GATE: v0.1.0 — Terraform Foundation & Shared Module
**Status:** WORK COMPLETE, ALL CRITERIA MET — awaiting GO certification.
CONFIRMED ✓ · ROADMAP APPROVED ✓ · build done · fmt/validate/tflint/checkov
green (270/0) · `terraform plan` clean in us-east-2 (74 add / 0 change / 0
destroy, account <ACCOUNT_ID>). Next gate on GO: **v0.2.0 Component A — Payment
Intake API + idempotency (commitment 1)**; its first task is the idempotency
backing-store decision (see ARCHITECTURE.md known-unknowns).

### Goal
Stand up the complete Terraform module skeleton for PrePayGuard so every later
gate has infrastructure to attach application code to. All modules author-complete
and `terraform plan`-clean against `environments/dev`. No Lambda application logic
yet (handlers are placeholder images or stubs); this gate is infrastructure shape.

### In scope (v0.1.0)
- `modules/queue_worker_stage/` **first** — the shared module (Lambda container, SQS in/out, DLQ + redrive, event source mapping, IAM role/policy, CloudWatch queue-depth alarm, conditional `secretsmanager:GetSecretValue` when `secrets_arn` non-null). Every other stage module depends on this pattern.
- `modules/api_intake_stage/` — API Gateway (AWS_IAM auth), Lambda, output SQS, DLQ.
- `modules/audit_store/` — S3 bucket, Object Lock enabled at creation, Compliance mode, default retention, deny-non-lock bucket policy.
- `modules/ecr_repo/` — shared, instantiated 4× (one per component image).
- `modules/review_queue/` — human-review SQS path fed by D.
- `environments/dev/` — `main.tf` wiring module instances + queue ARNs between stages, `variables.tf`, `outputs.tf`, `terraform.tfvars`, `backend.tf` (local backend for course scope, documented), `providers.tf`.
- Foundation docs seeded: `DECISIONS.md` (12 LOCKED, verbatim from decisions log), `ARCHITECTURE.md` skeleton, `.tflint.hcl`, `.checkov.yaml`, `.gitignore`, `README.md`.

### Explicitly NOT in v0.1.0 (deferred)
- Any Lambda handler business logic (idempotency, enrichment, scoring, disposition) → v0.2.0–v0.4.0.
- CI workflows and security scanners → v0.6.0.
- Real container image builds → per-component gates.
- The capstone handoff package → v1.0.0.

### Success criteria
- `terraform fmt -check` clean, `terraform validate` passes, `terraform plan` produces a coherent plan with no errors against `environments/dev`.
- `queue_worker_stage` proven reusable via `for_each` shape (even if instances are wired with placeholder image URIs this gate).
- DECISIONS.md contains all 12 entries as LOCKED.

## DECISIONS SNAPSHOT
12 of 12 LOCKED. Full text seeded into DECISIONS.md at foundation build.
No open architectural questions.
