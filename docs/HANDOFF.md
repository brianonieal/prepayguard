# PrePayGuard ("Treasury") — Capstone Handoff Package

**JHU Certificate in AI Engineering — CO.EN.AIE.LLL.2026.01**
**Author:** Brian Onieal · **Date:** 2026-07-03 · **Repo:** github.com/brianonieal/prepayguard (private)

A cloud-native pre-payment integrity screening pipeline modeled on the U.S. Treasury
Bureau of the Fiscal Service **Do Not Pay** program. Payments are screened before
disbursement: clean → approve, ambiguous → human review, improper → reject; every
decision is recorded immutably.

**Status at handoff:** all four graded commitments demonstrated — with **passing
automated tests and a live end-to-end run on real AWS** (us-east-2). CI green on
GitHub Actions. 14 architectural decisions locked and documented.

---

## 1. Architecture notes

*(Forward-looking — written as the system's designer documenting its shape, failure
modes, and untested paths; per DEC-11 / course objective 3.)*

### 1.1 System overview

```
caller (SigV4, payment-submitter role only — DEC-5)
  └─> API Gateway (AWS_IAM auth)
        └─> [A] Intake Lambda — payment-ID idempotency (commitment 1)   [DynamoDB]
              └─> SQS ─> [B] Enrichment — reference-source match          [bundled DNP list]
                    └─> SQS ─> [C] Risk Scoring — score + disposition
                          └─> SQS ─> [D] Disposition — audit + route + notify
                                 ├─> S3 Object Lock audit record (commitment 4)
                                 ├─> SQS review queue (ambiguous → human, commitment 2)
                                 └─> webhook (URL from Secrets Manager, DEC-7)
   [every SQS worker: DLQ + redrive (commitment 2); max-concurrency scaling
    + queue-depth alarm (commitment 3); least-privilege IAM]
```

Four **Lambda container images** (DEC-2), x86_64, `publish=true` behind a `live`
alias (DEC-10). Infrastructure is **Terraform** — one shared `queue_worker_stage`
module instantiated 3× via `for_each` for B/C/D (DEC-1), plus `api_intake_stage`,
`audit_store`, `ecr_repo` (4×), `review_queue`.

### 1.2 Components

| # | Component | Responsibility | Key decisions |
|---|---|---|---|
| A | Payment Intake API | IAM-authed intake; payment-ID idempotency; enqueue | DEC-5, DEC-13 |
| B | Enrichment & Reference-Match | Match payee against DNP-style reference sources | DEC-14 |
| C | Risk-Scoring & Decision | Rule-based score → three-way disposition | DEC-14 |
| D | Disposition Router & Audit Logger | Immutable audit write; route review; webhook notify | DEC-4, DEC-7 |

### 1.3 Message schema (grows across the pipeline)

```
A intake → { payment_id, payee, amount, payee_tin? }
B enrich → + enrichment { matches[{source,matched_on,confidence,severity}], match_count, highest_confidence }
C score  → + risk { score, disposition: approve|review|reject, reasons[] }
D audit  → audit record { schema_version, audit_id, payment_id, audited_at,
                          decision, evidence, payment, provenance, routing, integrity{sha256} }
```

### 1.4 Per-component failure modes

- **A — duplicate submission:** atomic DynamoDB conditional write with a PENDING→SENT
  state machine (DEC-13); a duplicate returns the *original* result, never a
  rejection or a second enqueue. A crash between the PENDING write and the SQS send
  is recovered by re-drive on retry (no silent loss). A is synchronous → no async
  DLQ; errors return to the caller as HTTP.
- **B / C — processing failure:** partial-batch failure reporting → SQS re-drive after
  `maxReceiveCount` (3) → the stage DLQ → DLQ-not-empty alarm (commitment 2).
- **C — unscorable payment:** fail-safe — anything not cleanly clean does not
  auto-approve; it becomes `review` (→ human) or re-drives to the DLQ.
- **D — audit write fails:** the message re-drives; a disposition never completes
  without an audit record (audit-first ordering).
- **D — webhook unreachable (DEC-7 risk):** review items could sit unnoticed;
  mitigated by an `ApproximateAgeOfOldestMessage` alarm on the review queue that does
  not depend on the webhook path.

### 1.5 Rollback (DEC-10)

Lambda **versions + aliases**, identical across all four components: each deploy
publishes a version, the `live` alias points at it, and rollback repoints the alias
to the prior version (seconds; no rebuild). Infrastructure rollback is via git —
every gate is tagged `syntaris-gate-vX.Y.Z`. Full runbook: `docs/ROLLBACK.md`.

### 1.6 Known unknowns (course objective 3)

- **Scaling shape under real load:** the `maximum_concurrency` scaling lever is
  deployed and config-verified; behavior under sustained high queue depth has not
  been stress-tested (see §6).
- **Reference-source fidelity:** B matches against a **bundled synthetic** DNP list
  (DEC-14), not a live data feed; production would integrate the real sources.
- **Cold-start latency (DEC-2 accepted risk):** container-image Lambdas cold-start
  slower than zip; acceptable for a screening pipeline, unmeasured under load.
- **Idempotency store durability:** DynamoDB is a short-lived dedup cache (TTL); the
  S3 Object Lock record is the canonical durable audit trail.

---

## 2. Tests

Full registry: `foundation/TESTS.md`. Runner: **pytest** (hermetic; moto-backed).
**29/29 passing** locally and in CI.

### 2.1 Graded-commitment evidence

| # | Commitment | Test file | Result |
|---|---|---|---|
| 1 | Idempotency (payment-ID dedup) | `tests/test_idempotency.py` (6) | PASS + **live** (duplicate replay) |
| 2 | Failure routing → manual review | `tests/test_failure_routing.py` (4) | PASS + **live** (review queue + webhook) |
| 3 | Queue-depth scaling | `tests/test_queue_depth_scaling.py` (3) | PASS (config proof via `terraform show -json`) |
| 4 | S3 Object Lock immutability | `tests/test_object_lock.py` (4) | PASS + **live** (delete + shorten-retention AccessDenied) |
| — | Review webhook + scoped secret (DEC-7) | `tests/test_review_notification.py` (4) | PASS + **live** (webhook.site capture) |
| — | Enrichment matching (DEC-14) | `tests/test_enrichment.py` (4) | PASS |
| — | Risk scoring / disposition (DEC-14) | `tests/test_risk_scoring.py` (4) | PASS |

Notable adversarial cases: concurrent-duplicate atomicity guard; crash-between-
PutItem-and-SQS-send recovery; audit-record integrity-hash verification.

### 2.2 Live end-to-end run (real AWS, 2026-07-03)

Three SigV4-signed payments through the deployed API (evidence:
`docs/evidence/live_e2e_run.txt`):

| Payment | Disposition | Live signals |
|---|---|---|
| clean vendor | **approve** (score 0) | audit record in Object Lock |
| TIN = 900000001 (synthetic DMF) | **reject** (score 95, TIN match) | audit record |
| payee "Acme Shell LLC" (name match) | **review** (score 60) | audit record + review-queue item + webhook POST captured |
| duplicate of the clean payment | idempotent replay | same `message_id`, not re-queued |

All three worker DLQs empty → clean processing. Separately, the live Object-Lock
proof (`docs/evidence/live_object_lock_proof.txt`) shows a real audit object refusing
both delete and shorten-retention.

---

## 3. Deployment documentation

### 3.1 Stack & regions

AWS-only, single account (<ACCOUNT_ID>), single region **us-east-2**, single `dev`
environment. Terraform ≥1.6 (validated on 1.15.7), AWS provider ~>5.0 (v5.100.0
pinned in the committed lockfile). Local state backend (course scope — documented in
`environments/dev/backend.tf`; a remote backend is the production upgrade).

### 3.2 Deploy procedure

Because Lambdas cannot be created before their images exist, deploy is staged:

```
cd environments/dev
terraform init
terraform apply -target=module.ecr           # 1. create the 4 ECR repos
# 2. build + push each image (Docker v2 schema-2 manifest — Lambda rejects OCI):
docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
  --output type=image,oci-mediatypes=false,push=true \
  -t <acct>.dkr.ecr.us-east-2.amazonaws.com/treasury-dev-<name>:bootstrap ./src/<component>
terraform plan -out=tfplan                    # 3. review
terraform apply tfplan                         # 4. apply the full stack
# 5. set the review webhook secret (out-of-band; never in Terraform/git):
aws secretsmanager put-secret-value --secret-id <arn> --secret-string <webhook-url>
```

`terraform apply` is always a **manual, deliberate action** — CI never auto-applies
(DEC-6). The audit bucket (`module.audit_store`) is applied first and is
**not destroyable** while Object Lock retention holds (DEC-4, by design).

### 3.3 CI/CD (DEC-6)

GitHub Actions, verified green:
- **`ci.yml`** (every push/PR): `terraform fmt/validate`, `tflint`, **pytest**,
  **ruff**, **pip-audit**, **checkov** — no AWS credentials required.
- **`plan.yml`** (PRs to main): `terraform plan` posted as a PR comment, **no
  auto-apply**. Requires an `AWS_PLAN_ROLE_ARN` OIDC secret (documented in-file).

### 3.4 Live endpoint (current deployment)

`POST https://0uhsehplg4.execute-api.us-east-2.amazonaws.com/dev/payments` —
SigV4-signed as `treasury-dev-payment-submitter` (DEC-5). Reference client:
`scripts/send_payment.py`.

---

## 4. Security findings

### 4.1 Narrative

The system has **zero failing** static-analysis findings across four tools
(checkov 289/0, ruff clean, pip-audit clean on all four runtimes, tflint 0). The
security posture is defense-in-depth:

- **Identity/auth (DEC-5):** API Gateway `AWS_IAM` (SigV4) + a resource policy
  scoping invoke to exactly one IAM role — verified live (a signed request from the
  submitter role succeeds; the policy denies all others).
- **Least privilege:** each component's execution role is scoped to only the
  resources it touches (e.g., only D can write the audit bucket and read the one
  webhook secret; B/C hold no secrets).
- **Immutability (DEC-4, commitment 4):** S3 Object Lock COMPLIANCE — **live-verified**
  that no principal, including account root, can delete or shorten a record.
  Plus a per-record SHA-256 integrity hash (content-tamper evidence).
- **Encryption:** audit bucket SSE-KMS with a rotating CMK; TLS-only bucket policy;
  public access fully blocked; SQS SSE.
- **Secrets (DEC-7):** the only secret (a webhook URL) lives in Secrets Manager, read
  via least-privilege `GetSecretValue` on one ARN; never in code, tfvars, or git.
- **Supply chain (DEC-8/9):** pip-audit + (planned) Grype on images; checkov + tflint
  + ruff in CI. ECR immutable tags + scan-on-push.

### 4.2 Risk-rating table

| Rating | Finding | Component | Remediation status |
|---|---|---|---|
| Low | No cross-region replication of the audit bucket (CKV_AWS_144, skipped) | audit_store | Accepted — single-region course scope; follow-on if DR required |
| Low | No S3 server-access logging on the audit bucket (CKV_AWS_18) | audit_store | Accepted — API access logging + CloudTrail cover caller audit |
| Low | API Gateway not behind a WAF (CKV2_AWS_29) | api_intake | Accepted — IAM auth + single-role resource policy bound the surface |
| Low | Idempotency table uses AWS-managed SSE, not a CMK (CKV_AWS_119) | api_intake | Accepted — dedup cache holds no amounts/PII; decision data is in the CMK-encrypted audit record |
| Low | Webhook secret has no auto-rotation (CKV2_AWS_57) | env | Accepted — a webhook URL is not a rotating credential |
| Info | GitHub Actions use Node20 (deprecation notice) | CI | Follow-on — bump action major versions |
| Info | Terraform local state backend | env | Follow-on — move to remote state for multi-operator use |

Full raw scan output: **Appendix A**. Every skip carries an in-file justification in
`.checkov.yaml`.

---

## 5. Residual risks

*(Scoped generally, not only to gaps closed during the build — per DEC-11.)*

1. **Synthetic reference data:** B screens against a bundled fake list, not live DNP
   sources; false-positive/negative rates are not representative of production.
2. **Local Terraform state:** no locking/remote state — safe for one operator, unsafe
   for a team or CI applies.
3. **Webhook single point of notification (DEC-7):** if the endpoint is
   mis/unconfigured, review items rely on the age-of-oldest-message alarm as the only
   backstop.
4. **No load/DR testing:** scaling behavior and multi-AZ/region failure modes are
   designed but unverified under stress.
5. **Cold-start latency (DEC-2):** accepted for a screening pipeline; unmeasured.
6. **Plan-on-PR fidelity:** with a local backend, CI plan shows a full create-diff
   rather than real drift until a remote backend is adopted.

---

## 6. Recommended follow-on work

1. **Integrate real reference sources** (SSA DMF, SAM.gov, TOP, OIG LEIE) behind
   Component B, with proper record-linkage and match-confidence tuning.
2. **Remote Terraform state** (S3 backend with native lockfile) + the
   `AWS_PLAN_ROLE_ARN` OIDC role so `plan.yml` reflects real drift.
3. **Grype image scanning** in CI now that images exist; bump Actions off Node20.
4. **Load & chaos testing** to validate commitment-3 scaling and DLQ behavior under
   sustained depth; measure cold-start latency and right-size memory/concurrency.
5. **Reviewer tooling** for the human-review queue (currently console/CLI drain).
6. **Multi-region / DR** for the audit store if retention SLAs demand it.
7. **A second notification path** (e.g., scheduled review-queue-depth check) to
   harden DEC-7 beyond the single webhook.

---

## Appendix A — Raw scan output (2026-07-03)

```
checkov  : Passed 289, Failed 0, Skipped 3   (config .checkov.yaml; all skips justified in-file)
ruff     : All checks passed!                (src + tests; config ruff.toml)
pip-audit: No known vulnerabilities found    (all 4 component requirements.txt)
tflint   : 0 issues                          (recursive; ruleset-aws 0.48.0)
terraform fmt -check / validate: clean       (aws provider v5.100.0)
GitHub Actions ci.yml: green (both jobs)
```

## Appendix B — Evidence files

- `docs/evidence/live_object_lock_proof.txt` — real delete/shorten AccessDenied
- `docs/evidence/live_e2e_run.txt` — three-payment live run + audit records
- Decisions: `foundation/DECISIONS.md` (14 LOCKED) · Changelog: `foundation/CHANGELOG.md`
