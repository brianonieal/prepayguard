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

Automatic inputs (scheduled, EventBridge):
  [E] Batch Ingest (S3-triggered CSV/Excel/JSON) reuses A's queue + idempotency table (DEC-16)
  [F] Feeder  (business-hours ET) ─> pulls real USAspending awards ─> drops a file for [E]
  [G] Refresher (daily) ─> re-pulls real SAM.gov exclusions ─> re-embeds ─> republishes the
                           versioned reference list (only when it changed)
```

The system now has seven Lambda components: the five-stage screening path
(A intake, B enrichment, C scoring, D disposition, E batch ingest) plus two
scheduled data feeders (F feeder, G refresher). All are Lambda **container
images** (DEC-2), x86_64 uniformly, deployed with `publish = true` behind a
`live` alias (DEC-10). Infrastructure is Terraform: one shared
`queue_worker_stage` module instantiated 3× via `for_each` for B/C/D, plus
`api_intake_stage`, `batch_ingest_stage`, `scheduled_feeder`,
`scheduled_refresher`, `audit_store`, `review_queue`, `console_foundation`,
`console_api`, `reference_store`, and `ecr_repo` (8×, one per component). The
console API and the React console (§8) sit on top for human adjudication.

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
- **Malformed / oversized / non-Latin `payee`** (Phase 2.1e, DEC-29): payee input
  validation, flag-gated `payee_validation_enabled` (default ON). Two layers that
  toggle together — the API Gateway request model (`maxLength` 35 sized to the
  Fedwire beneficiary-name field + printable-ASCII `pattern`) and the handler's
  `_validate_payee`, which returns **400 before any enqueue** (fail-closed: an
  invalid payee is never screened, never approved). This is the primary remediation
  for the F1 matcher-evasion root cause — Component A previously accepted unbounded
  free text (`INJECTION_THREAT_MODEL.md`, 2.1a/2.1c). **KNOWN LIMITATION:** it does
  NOT close F1 — 75/96 listed entities remain evadable via an in-budget ASCII append
  (2.1d), and ASCII-only rejects legitimate diacritic names; the windowed matcher is
  the recommended, un-built backstop. Flag off restores the pre-2.1e behavior for the
  demo attack.

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

### E. Batch Ingest (DEC-16)
- **Malformed file / bad rows**: per-row validation collects errors without
  failing the whole file; a required-field-missing or non-numeric-amount row is
  reported in the batch summary, not silently dropped. Unsupported formats are
  reported, never dropped.
- **Duplicate rows across batches**: the SAME idempotency table and PENDING→SENT
  state machine as A, so an overlapping row dedupes rather than double-screens.
- **S3 event delivery**: at-least-once; a re-delivered object re-enters the
  idempotency guard, so re-ingest is safe.

### F. Feeder (DEC-23)
- **USAspending unavailable / API drift**: the scheduled run wraps the fetch in
  try/except, logs, and SKIPS the run; it never crashes the schedule or writes a
  partial file. Mapping tolerates missing award fields (drops awards missing a
  name/id or with a non-positive amount).
- **Volume / immutable-audit growth**: bounded by a per-run size cap plus the
  `enabled` stop switch; each pulled payment is a permanent audit record, so the
  cap and the dev 1-day retention bound the growth (see §4).
- **Deterministic ids**: `USASPEND-{award id}` so overlapping pulls dedupe via the
  shared idempotency table.

### G. Refresher (DEC-24)
- **SAM source unavailable / empty / unchanged**: degrades to a no-op that keeps
  the current reference version (`{"refreshed": false, ...}`); it republishes only
  when the SAM list actually changed (compared on name+UEI keys), so it never
  churns versions or manufactures flags.
- **Concurrent publish**: versioned reference writes use an `IfNoneMatch="*"`
  conditional put, so a racing publish fails closed rather than clobbering.

## 3. Rollback mechanism (DEC-10)

One mechanism, identical across every Lambda component:

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
- Human reviewers drain the review queue through the reviewer console (§8), the
  React/Vite SPA shipped in Phase 2 and extended through Phase 5. (This assumption
  originally read "no reviewer UI" when the project was backend-only at Phase 1; the
  console has since been built, deployed, and is live.)

## 7. Message schema (grows across the pipeline)

Each stage adds a block; nothing is removed, so the audit record is the full trail.

```
A intake  → { payment_id, payee, amount, payee_tin?, submitted_by }
              (submitted_by = caller identity, carried through for the maker/checker
               segregation-of-duties check at review time, DEC-17)
B enrich  → + enrichment { matches[{source, matched_on, confidence, severity,
                                     similarity?, reference_version}],
                           match_count, highest_confidence }
              (matched_on is one of tin_exact, name_exact, name_fuzzy, name_semantic;
               similarity is the raw cosine for a name_semantic hit, DEC-19)
C score   → + risk { score, disposition: approve|review|reject, reasons[] }
D audit   → audit record { schema_version, audit_id, payment_id, audited_at,
                           decision, evidence, payment, provenance, routing,
                           integrity{ sha256 } }  (written to S3 Object Lock)
```

- **B (DEC-14):** TIN match → conf 95, exact name → 80, fuzzy (difflib ≥0.9) → 60;
  a Bedrock-embedding `name_semantic` net (DEC-19) runs only when the string rules
  miss and is capped to REVIEW by C.
- **C (DEC-14):** TIN match → `reject`; name match → `review` (potential match →
  human, feeds commitment 2); no match → `approve`. Thresholds: ≥80 reject,
  ≥30 review, else approve; name matches capped at 60 to keep them in review.
- **D:** audit-first (authoritative) then route; `integrity.sha256` is computed
  over all record fields except `integrity` (sorted-key compact JSON).

## 8. Treasury Console (introduced Phase 2, v1.1.0 to v1.4.0; extended through Phase 5)

A React/Vite SPA on **S3 + CloudFront** — the human surface over the pipeline.
Introduced in Phase 2 and extended since: roles + segregation of duties and the
read-only auditor (Phase 3), versioned reference-data editing, semantic-match
evidence and LLM briefs (Phase 3), the analytics/compliance and audit-log surfaces
(Phase 3-4), the admin **Feed** builder that configures Component F (Phase 5,
v3.5.0-v3.6.0), and the v3.7.0 restructure into three surfaces (Dashboard / Review
Queue / Audit log) with admin config under an Admin menu and submission as a modal.

```
Browser SPA (CloudFront)
  └─ Cognito User Pool (SRP login) → Identity Pool → temp IAM creds (DEC-15)
       ├─ SigV4 → intake API  POST /payments            (submit form + batch CSV)
       └─ SigV4 → console API  (console role only):
            GET  /reviews                       list the reviews DynamoDB table
            GET  /audit/{payment_id}            fetch the Object Lock audit record
            POST /reviews/{id}/decision         reviewer approve/reject (+ its own audit record)
            GET/POST /reviews/{id}/attachments  presigned S3 case-document uploads
```

- **Reviews table:** Component D writes a queryable review item (payee, match,
  score, status) alongside the SQS hand-off, so the dashboard can list without
  scanning S3. SQS stays the durable path.
- **Reviewer decisions are audited:** each approve/reject writes an integrity-
  hashed decision record to the same Object Lock bucket — the compliance story
  extends to human actions.
- **Client-side integrity verify:** the browser recomputes the audit record's
  SHA-256 and compares to the stored hash (✓/✗), making immutability clickable.
- **Auth (DEC-5 reuse, DEC-15):** every call is AWS_IAM/SigV4 — same mechanism as
  the machine endpoints, no second authorizer.
- **Known unknown:** JS↔Python canonicalization for hash-verify (float/unicode) —
  demo uses integer amounts; production hardening in v1.5.0 (noted).
- **Scale note:** reviews `Scan` + audit S3 prefix-scan are course-scale; bulk
  hardening (pagination, `payment_id` audit index, S3 batch ingestion, bulk
  actions) is the deferred v1.5.0 gate.

