# ARCHITECTURE.md — PrePayGuard ("Treasury")

Forward-looking design documentation (DEC-11: written as the system's designer
documenting failure modes and untested paths — not as discovery of an inherited
system). Grows at every gate; feeds the capstone handoff package directly.

## 1. System overview

Cloud-native pre-payment integrity screening pipeline modeled on the U.S.
Treasury Bureau of the Fiscal Service **Do Not Pay** program. Payments are
screened *before* disbursement: clean payments auto-approve, ambiguous payments
route to human review, bad payments are rejected. Every disposition is recorded
immutably.

```
caller (SigV4, payment-submitter role only — DEC-5)
  └─> API Gateway (AWS_IAM auth)
        └─> [A] Intake Lambda — payment-ID idempotency (commitment 1)
              └─> SQS: intake-out
                    └─> [B] Enrichment Lambda — reference-source matching
                          └─> SQS: enrichment-out
                                └─> [C] Risk-Scoring Lambda — score + disposition decision
                                      └─> SQS: risk-scoring-out
                                            └─> [D] Disposition Lambda
                                                  ├─> S3 Object Lock audit bucket (COMPLIANCE — commitment 4)
                                                  ├─> SQS: review queue (ambiguous → human — commitment 2)
                                                  └─> webhook notify (URL from Secrets Manager — DEC-7)
   [every SQS-triggered stage: DLQ + redrive (commitment 2),
    max-concurrency scaling + queue-depth alarm (commitment 3)]
```

All four components are Lambda **container images** (DEC-2), x86_64 uniformly,
deployed with `publish = true` behind a `live` alias (DEC-10). Infrastructure
is Terraform: one shared `queue_worker_stage` module instantiated 3× via
`for_each` for B/C/D, plus `api_intake_stage`, `audit_store`, `ecr_repo` (4×),
and `review_queue` (DEC-1).

## 2. Component failure modes

Stubs at v0.1.0; each component's gate (v0.2.0–v0.4.0) fleshes out its section
with observed behavior, not speculation.

### A — Payment Intake API
- **Duplicate submission** (retry storms, client bugs): atomic DynamoDB
  conditional write (DEC-13). A duplicate `payment_id` returns the ORIGINAL
  result (idempotent replay), never a rejection or a second enqueue. If a prior
  attempt died after the PENDING write but before the SQS send, a retry finds
  the PENDING record and re-drives the send — no silent loss.
- **Unauthorized caller**: rejected at the gateway by AWS_IAM auth + resource
  policy (only the payment-submitter role); never reaches the Lambda.
- **Output queue unavailable / send fails**: synchronous path — caller receives
  an error and retries; no silent loss. No async DLQ exists on A by design
  (sync invocation), documented in `modules/api_intake_stage/main.tf`.

### B — Enrichment & Reference-Match
- **Reference source unavailable or malformed payload**: processing failure →
  SQS redrive after 3 receives → B's DLQ → DLQ alarm (commitment 2).
- **Slow enrichment under load**: queue depth grows → depth alarm; concurrency
  scales to `maximum_concurrency` (commitment 3).

### C — Risk-Scoring & Decision Engine
- **Scoring error / unclassifiable payment**: fail-safe posture — anything the
  engine cannot score cleanly must NOT auto-approve; it becomes an ambiguous
  disposition (→ human review at D) or a redrive → DLQ. *(Decision logic at v0.3.0.)*

### D — Disposition Router & Audit Logger
- **Audit write fails**: message returns to queue (redrive → DLQ after 3) —
  a disposition without an audit record must never complete silently.
- **Webhook unreachable** (DEC-7 acknowledged risk): review items could sit
  unnoticed. Mitigation built at v0.1.0: `ApproximateAgeOfOldestMessage` alarm
  on the review queue (4h threshold) — the fallback does not depend on the
  webhook path.
- **Retention misconfiguration** (DEC-4 acknowledged risk): see §4 — the one
  irreversible surface in the system.

## 3. Rollback mechanism (DEC-10)

One mechanism, identical across all four components:

1. Every deploy publishes a numbered Lambda **version** (`publish = true`).
2. The **`live` alias** points at exactly one version. API Gateway (A) and all
   event source mappings (B/C/D) bind to the alias, never `$LATEST`.
3. **Rollback = repoint the alias to the prior version** — one
   `aws lambda update-alias` call or a one-line Terraform change. No
   infrastructure destroy/recreate (rejected in DEC-10 as too coarse).

Infrastructure-level mistakes roll back via git: every gate is tagged
(`syntaris-gate-vX.Y.Z`); `terraform plan` against a checked-out tag shows the
exact reversion diff before any apply.

## 4. Irreversibility register

| Surface | Why irreversible | Guard |
|---|---|---|
| S3 Object Lock COMPLIANCE retention (audit bucket) | Once an object version is written, NO principal — including account root — can shorten or remove its retention; AWS Support cannot override. | `retention_days` has no default (must be an explicit tfvars act); dev = 1 day; real value is a sign-off gate before the v0.4.0 apply; days-vs-years unit chosen deliberately (they differ by leap days). Checkov watches the lock config (DEC-9). **Live-verified immutable 2026-07-03** — a real object's delete and shorten-retention were both AccessDenied (`docs/evidence/live_object_lock_proof.txt`). |

## 5. Known unknowns (course objective 3)

- **Idempotency backing store — RESOLVED (DEC-13):** DynamoDB conditional write
  with a PENDING→SENT state machine and original-result replay. The table is a
  short-lived dedup cache (TTL); Component D's S3 Object Lock write is the
  canonical audit record, so the two retention models don't conflict. SQS FIFO
  dedup, S3 If-None-Match, and Lambda Powertools were considered and rejected
  (see DEC-13).
- **ECR digest pinning trap (recorded from the v0.1.0 grounding review):** the
  `aws_ecr_image` data source does **not** export `image_digest` — the manifest
  digest is its `id` attribute, and `code_sha256` is the preferred
  container-image update trigger on `aws_lambda_function`. Applies from the
  first real image build (v0.2.0). Wrong usage fails at apply/invoke, not plan.
- **moto vs. real Object Lock semantics:** unit tests assert lock behavior
  against local fakes; where fake behavior diverges from real COMPLIANCE-mode
  enforcement, the divergence is documented and verified once against a live
  dev bucket during v0.4.0 (TESTS.md policy).
- **SQS→Lambda scaling shape under `maximum_concurrency`:** the scaling *lever*
  exists at v0.1.0; how visibly queue depth translates to concurrency at
  course-scale load determines the commitment-3 test design (v0.5.0).
- **Cold-start latency of container images** (DEC-2 accepted risk): acceptable
  for a screening pipeline; measure real numbers once components exist, so the
  handoff package reports data instead of the assumption.

## 6. Assumptions

- Single AWS account, single region (us-east-2), single `dev` environment;
  free-tier credits bound all sizing choices.
- Single operator (Brian) — local Terraform state is deliberate (see
  `environments/dev/backend.tf`); CI is plan-only (DEC-6).
- x86_64 for all images (declared on every function to prevent platform
  mismatch at invoke; arm64 cost optimization noted for follow-on work).
- Human reviewers drain the review queue via console/CLI for course scope — no
  reviewer UI exists or is planned (backend-only project).

## 7. Message schema (grows across the pipeline)

Each stage adds a block; nothing is removed, so the audit record is the full trail.

```
A intake  → { payment_id, payee, amount, payee_tin? }
B enrich  → + enrichment { matches[{source,matched_on,confidence,severity}], match_count, highest_confidence }
C score   → + risk { score, disposition: approve|review|reject, reasons[] }
D audit   → audit record { schema_version, audit_id, payment_id, audited_at,
                           decision, evidence, payment, provenance, routing,
                           integrity{ sha256 } }  (written to S3 Object Lock)
```

- **B (DEC-14):** TIN match → conf 95, exact name → 80, fuzzy (difflib ≥0.9) → 60.
- **C (DEC-14):** TIN match → `reject`; name match → `review` (potential match →
  human, feeds commitment 2); no match → `approve`. Thresholds: ≥80 reject,
  ≥30 review, else approve; name matches capped at 60 to keep them in review.
- **D:** audit-first (authoritative) then route; `integrity.sha256` is computed
  over all record fields except `integrity` (sorted-key compact JSON).

