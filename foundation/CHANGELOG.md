# CHANGELOG.md — PrePayGuard ("Treasury")

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

### Fixed during verification (checkov triage)
- API resource policy: wildcard-principal Allow tightened to the submitter role
  (CKV_AWS_283); `create_before_destroy` on the REST API (CKV_AWS_237).
- Audit CMK: explicit key policy (CKV2_AWS_64); bucket lifecycle rules (CKV2_AWS_61).
- **Latent v0.4.0 runtime bug caught:** Component D's role lacked
  `kms:GenerateDataKey`/`kms:Decrypt` on the audit CMK — SSE-KMS audit writes
  would have failed at first invoke. Conditional KMS statement added to the
  shared module.

### Known / deferred
- `terraform plan` pending AWS credentials (aws CLI not installed) — surfaced
  at gate close.
- Recorded for v0.2.0: `aws_ecr_image` exports the digest as `id` (NOT
  `image_digest`); prefer `code_sha256` as the image-update trigger.
  Request-validator (CKV2_AWS_53) lands with the payment schema at v0.2.0.
