# PrePayGuard ("Treasury"): Capstone Handoff Package

**JHU Certificate in AI Engineering, CO.EN.AIE.LLL.2026.01**
**Author:** Brian Onieal · **Repo:** github.com/brianonieal/prepayguard (private)
**Original package:** 2026-07-03 (v1.0.0) · **Refreshed:** 2026-07-07 (through v3.7.1: automated data feeds + console restructure)

A cloud-native pre-payment integrity screening pipeline modeled on the U.S. Treasury
Bureau of the Fiscal Service **Do Not Pay** program. Payments are screened before
disbursement: clean → approve, ambiguous → human review, improper → reject; every
decision is recorded immutably, and every disposition cites the exact screening-list
version it was judged against.

**Status at this refresh:** everything through Phase 5 (v3.7.1) is complete and **live
on AWS** (us-east-2), console at **https://d2rbxaf6pqgvb1.cloudfront.net**. **27
architectural decisions locked.** Verified green: **pytest 135/135, console vitest
34/34, checkov clean, ruff clean, terraform validate clean.** The one differentiating
component (the semantic matcher) is **measured**, the screening list includes **one
real federal source** (SAM.gov exclusions) alongside three modeled ones and is kept
current automatically by a daily refresher, and real federal payments now flow in
automatically on a schedule via the USAspending feeder (no manual upload).

---

## 1. Architecture notes

*(Forward-looking, written as the system's designer documenting its shape, failure
modes, and untested paths; per DEC-11 / course objective 3. Full analysis:
`ARCHITECTURE.md` and `docs/sme/ORIENTATION.md`.)*

### 1.1 System overview

```
caller (SigV4) ─> API Gateway (AWS_IAM) ─> [A] Intake, payment-ID idempotency  [DynamoDB]
  └─> SQS ─> [B] Enrichment, reference match: TIN/name exact, fuzzy, SEMANTIC   [versioned S3 list + Bedrock]
        └─> SQS ─> [C] Risk Scoring, rule-based score + disposition
              └─> SQS ─> [D] Disposition, audit + route + notify
                     ├─> S3 Object Lock audit record (commitment 4)
                     ├─> SQS review queue (ambiguous → human, commitment 2)
                     └─> webhook (URL from Secrets Manager, DEC-7)
[E] Batch Ingest (S3-triggered CSV/Excel/JSON) reuses A's queue + idempotency table (DEC-16)
[F] Feeder (EventBridge, business-hours ET) → pulls real USAspending awards → drops a file for [E] (DEC-23)
[G] Refresher (EventBridge, daily) → re-pulls real SAM.gov exclusions → re-embeds → republishes the versioned list on change (DEC-24)
Console API (AWS_IAM): reviews, audit, decisions, batches, reference publish, feed config, LLM briefs, analytics
Reviewer Console: React/Vite SPA on S3 + CloudFront; Cognito → temp IAM creds → SigV4 (DEC-15)
```

Seven Lambda container images (DEC-2) plus a console API, x86_64, `publish=true` behind
a `live` alias (DEC-10). Terraform: shared `queue_worker_stage` module 3× via `for_each`
for B/C/D (DEC-1), plus `api_intake_stage`, `batch_ingest_stage`, `scheduled_feeder`,
`scheduled_refresher`, `audit_store`, `review_queue`, `console_foundation`,
`console_api`, `reference_store`, `ecr_repo` (8×).

### 1.2 Components

| # | Component | Responsibility | Key decisions |
|---|---|---|---|
| A | Payment Intake API | IAM-authed intake; payment-ID idempotency (PENDING→SENT); enqueue | DEC-5, DEC-13 |
| B | Enrichment & Reference-Match | Match payee/TIN: TIN/name exact, fuzzy, and Bedrock-embedding **semantic** | DEC-14, DEC-18, DEC-19 |
| C | Risk-Scoring & Decision | Transparent rule-based score → three-way disposition | DEC-14 |
| D | Disposition Router & Audit Logger | Immutable audit write; route review; webhook notify | DEC-4, DEC-7 |
| E | Batch Ingest | S3-triggered bulk CSV/Excel/JSON; reuses A's queue + idempotency table | DEC-16 |
| F | Feeder | Scheduled USAspending pull (business-hours ET), drops a file for E; deterministic ids dedupe | DEC-23, DEC-25, DEC-26 |
| G | Refresher | Scheduled daily SAM.gov re-pull, re-embed, republish the versioned list only on change | DEC-24 |
|, | Console API | Reviews, audit, decisions, batches, reference publish, feed config, LLM briefs, analytics | DEC-15, DEC-17..27 |

### 1.3 Screening intelligence (Phase 3)

- **Rule-based matching (DEC-14):** TIN exact → 95, name exact → 80, fuzzy (difflib
  ≥0.90) → 60; C maps TIN→reject, name→review (potential match to a human), none→approve.
- **Semantic matching (DEC-19):** Bedrock Titan Embed v2 cosine over per-entry vectors
  stored IN the versioned reference document (no vector DB). Runs only when string rules
  miss; capped to REVIEW by C. **Measured**, see §7.
- **Versioned reference data (DEC-18):** admins publish new lists through the console;
  each screening cites the exact list version. Store: `reference/current.json` +
  immutable `reference/versions/{N}.json`.
- **One real source, three synthetic (DEC-22), stated plainly:** only the **SAM.gov
  exclusions** (federal debarment list) are real, ingested by `scripts/ingest_sam_exclusions.py`
  and refreshed by Component G. The other three, **SSA Death Master File (DMF)**, **Treasury
  Offset Program (TOP)**, and **OIG LEIE**, are **synthetic fixtures with fabricated entries**
  (`src/component_b_enrichment/reference_data.json`, self-labeled). DMF and TOP are **not
  publicly obtainable** (DMF access is restricted to certified users under the DPPA/NTIS
  program; TOP is an internal Treasury offset system), which is precisely why they are
  modeled rather than integrated. OIG LEIE is public but is kept synthetic here for
  consistency with the other restricted feeds. See §8 and `docs/sme/REAL_SOURCE_INGEST.md`.
- **LLM adjudication briefs (DEC-20):** on-demand Bedrock Nova Lite summary for reviewers,
  grounded only in the audit record, advisory, never written to the immutable record.

### 1.4 Console, roles, and oversight (Phases 2-4)

- **Auth (DEC-15):** Cognito → Identity Pool → temporary IAM creds → browser SigV4; one
  AWS_IAM model for machine and human callers, no second authorizer.
- **Roles + segregation of duties (DEC-17):** submitter / reviewer / admin / read-only
  auditor via Cognito groups → per-group IAM roles; an approver cannot decide a payment
  they submitted (enforced in the handler, not just IAM).
- **Analytics + auditor (DEC-21):** throughput, disposition mix, hit rate, queue aging,
  reviewer productivity; read-only auditor role; client-side audit-log CSV export.
- **Phase 4:** executive Overview tab, admin demo-reset (never touches Object Lock),
  Profile self-service (password change, optional TOTP MFA).
- **Phase 5 (automated data + restructure):** the USAspending feeder (F, DEC-23) on a
  business-hours schedule and the daily SAM refresher (G, DEC-24) make both sides of the
  data automatic; the in-console **Feed** builder (DEC-25/26) gives admins the full
  USAspending search surface (award types, agency/sub-agency, location, date range) that
  drives what F pulls (Save for the schedule, Run-now on demand); v3.7.0 (DEC-27)
  restructures the console into three surfaces plus an Admin menu. Feed control is
  admin-only, enforced at the resource-policy edge (`Deny` non-admin on `/feed/*`) and in
  the handler.

### 1.5 Rollback (DEC-10)

Lambda **versions + aliases**, identical across components: rollback repoints the `live`
alias to the prior version (seconds, no rebuild). Reference-data rollback: repoint
`current.json` to a prior `versions/{N}.json`. Infra rollback via git (every gate tagged
`syntaris-gate-vX.Y.Z`). Runbook: `docs/ROLLBACK.md`.

### 1.6 Known unknowns (course objective 3)

- Semantic layer accuracy on real/large lists (the §7 eval is on a small synthetic set;
  no adversarial name obfuscation).
- Real-source fidelity: one real source (SAM) is capped to a demo-sized slice; three
  remain synthetic (DEC-22).
- Scaling under sustained load, cold-start latency: designed/configured, unmeasured
  under stress.
- JS↔Python hash canonicalization for client-side integrity verify (demo uses integer
  amounts; v1.5.0 hardening note).

---

## 2. Tests

Runner: **pytest** (hermetic, moto-backed) + console **vitest**. **pytest 135/135,
vitest 34/34**, both green locally and in CI. Registry: `foundation/TESTS.md`.

### 2.1 Graded-commitment evidence

| # | Commitment | Test file | Result |
|---|---|---|---|
| 1 | Idempotency (payment-ID dedup) | `test_idempotency.py` | PASS + **live** (replay) |
| 2 | Failure routing → manual review | `test_failure_routing.py` | PASS + **live** |
| 3 | Queue-depth scaling | `test_queue_depth_scaling.py` | PASS (config proof) |
| 4 | S3 Object Lock immutability | `test_object_lock.py` | PASS + **live** (delete + shorten AccessDenied) |
|, | Review webhook + scoped secret (DEC-7) | `test_review_notification.py` | PASS + **live** |
|, | Enrichment + semantic matching | `test_enrichment.py` | PASS |
|, | Risk scoring / disposition | `test_risk_scoring.py` | PASS |
|, | Batch ingest (DEC-16) | `test_component_e.py` | PASS |
|, | Console API (roles, briefs, analytics, reference) | `test_console_api.py` | PASS |
|, | Semantic-eval metric math (objective 5) | `test_semantic_eval.py` | PASS |
|, | Real SAM ingestion (objective 10) | `test_sam_ingest.py` | PASS |
|, | Feeder: USAspending pull, mapping, config (F) | `test_feeder.py` | PASS + **live** |
|, | Refresher: SAM re-pull, change-only publish (G) | `test_refresher.py` | PASS + **live** |

### 2.2 Live end-to-end (real AWS)

- Backend three-payment run: `docs/evidence/live_e2e_run.txt`.
- Console signed-in flow (login → submit → review → decide): `docs/evidence/console_live_e2e.txt`.
- Object Lock immutability: `docs/evidence/live_object_lock_proof.txt` (delete + shorten both AccessDenied).
- **Real-source screening (2026-07-06):** a real SAM.gov exclusion
  ("YATAI SMART INDUSTRIAL NEW CITY") screened through the full pipeline into the live
  console as a `name · sam_exclusions` review at reference version 4:
  `docs/evidence/live_real_source_ingest.txt`.

---

## 3. Deployment documentation

- **Stack:** AWS-only, single account (<ACCOUNT_ID>), region **us-east-2**, `dev`
  environment. Terraform ≥1.6, AWS provider ~>5.0 (pinned lockfile). Local state (course
  scope; remote state is the production upgrade).
- **Live console:** `https://d2rbxaf6pqgvb1.cloudfront.net` (Cognito login; operator-
  provisioned users; roles submitter/reviewer/admin/auditor). Verified serving 2026-07-06.
- **Intake API:** `POST https://0uhsehplg4.execute-api.us-east-2.amazonaws.com/dev/payments`,
  SigV4 as `treasury-dev-payment-submitter` (DEC-5). Client: `scripts/send_payment.py`.
- **Deploy:** staged (create ECR repos → `scripts/build-push-images.sh` → `terraform
  apply` → `scripts/deploy-console.sh`). `terraform apply` is always manual (DEC-6, CI
  is plan-only). Bedrock: `amazon.titan-embed-text-v2:0` + `amazon.nova-lite-v1:0`. The
  audit bucket is not destroyable while Object Lock holds (DEC-4, by design). The deploy
  scripts (`build-push-images.sh`, `deploy-console.sh`) resolve account/region/bucket/
  distribution/repos from `terraform output`; the seed/ingest/verify scripts take the
  bucket or endpoints as an argument or env var, filled from `terraform output` in the
  runbook. **Fresh-account setup runbook (Bedrock enablement, images, apply, secret,
  seed, users, console, verify): `docs/BOOTSTRAP.md`.**
- **CI/CD (DEC-6):** GitHub Actions, `ci.yml` (fmt/validate/tflint/pytest/ruff/pip-audit/
  checkov, no creds) and `plan.yml` (terraform plan on PRs, no auto-apply).

---

## 4. Security findings

Zero failing static-analysis findings across checkov, ruff, pip-audit, tflint. Posture is
defense-in-depth:

- **Identity/auth (DEC-5/15/17):** API Gateway AWS_IAM (SigV4) + resource policies scoping
  invoke to named roles; console uses Cognito → temp IAM creds → SigV4; role-based access
  with maker/checker segregation of duties enforced in the handler.
- **Least privilege:** each execution role scoped to only the resources it touches (only D
  writes the audit bucket and reads the one webhook secret; B reads the reference bucket
  and invokes Bedrock; B/C hold no secrets).
- **Immutability (DEC-4):** S3 Object Lock COMPLIANCE, live-verified no principal can
  delete or shorten a record; per-record SHA-256 integrity hash.
- **Encryption:** audit bucket SSE-KMS (rotating CMK), TLS-only, public access blocked;
  SQS SSE.
- **Secrets (DEC-7/22):** the webhook URL and any external API key live in Secrets Manager
  / gitignored local files, never in code or git.
- **Supply chain (DEC-8/9):** pip-audit + checkov + tflint + ruff in CI; ECR immutable
  tags + scan-on-push.
- **Responsible AI:** the reviewer brief (DEC-20) is advisory only, grounded in the audit
  record, and never written to S3/the audit record/the decision (code-verified,
  `docs/sme/BEDROCK_COST.md` §5). The semantic matcher only ever adds a REVIEW flag.

### 4.1 Risk-rating table (DEC-11)

Findings rated High / Medium / Low by likelihood × impact at course scope. **No High-
severity finding is open:** the load-bearing controls (AWS_IAM auth + resource-policy
scoping, Object Lock COMPLIANCE immutability live-verified, SSE-KMS, maker/checker
segregation of duties) are in place and evidenced. The open items are Medium/Low
hardening, observability, and scope, each with a remediation status.

| # | Finding | Area / component | Severity | Status | Evidence |
|---|---|---|---|---|---|
| 1 | CloudWatch alarms (queue-depth, DLQ-not-empty) have no notification target (`alarm_actions` empty); an operator is not paged when a DLQ fills | Observability / B-C-D, review queue | **Medium** | Open (follow-on: wire an SNS topic). Partial backstop: the review queue's `ApproximateAgeOfOldestMessage` alarm covers the human-review path | `modules/queue_worker_stage/main.tf` (alarms), DEC-19 |
| 2 | Console JS dependencies are not CVE-scanned in CI (`npm ci --no-audit`, no Dependabot); Python side is covered by `pip-audit --strict` | Supply chain / console | **Medium** | Open (follow-on: enable `npm audit` / Dependabot) | `.github/workflows/ci.yml` |
| 3 | Local Terraform state; safe for one operator, unsafe for team/CI applies | Deployment / state | **Medium** | Accepted at course scope; remote state + OIDC plan role is the production upgrade | `environments/dev/backend.tf`, `plan.yml` |
| 4 | One real screening source (SAM exclusions) capped to a demo-sized slice; three sources remain synthetic | Data fidelity / reference list | **Medium** | Accepted / documented; full extract + record linkage is follow-on | DEC-22, `docs/sme/REAL_SOURCE_INGEST.md` |
| 5 | Semantic-matcher accuracy measured only on a 27-case synthetic set; no adversarial name obfuscation; English/Latin only | Model evaluation scope | **Medium** | Accepted / measured + scoped (precision 0.83 / recall 1.00 / F1 0.91) | `docs/sme/SEMANTIC_EVAL.md` §7 |
| 6 | Bedrock is a soft dependency in B; an outage silently degrades the semantic net to rule-based screening | Availability / component B | **Low** | Mitigated: fails safe to deterministic rules (not blind); a Bedrock-availability alarm is follow-on | `src/component_b_enrichment/app.py` (semantic degrade) |
| 7 | Single webhook notification path for review routing (DEC-7) | Review routing / component D | **Low** | Mitigated by the age-of-oldest-message alarm; a second path is follow-on | DEC-7, `modules/review_queue/main.tf` |
| 8 | MFA is optional (opt-in TOTP), not enforced | Identity / Cognito | **Low** | Accepted; operator-provisioned users only, no public sign-up | `modules/console_foundation/main.tf` |
| 9 | `OPTIONS` preflight is unauthenticated (`Principal:"*"`, MOCK integration, no data path) for browser CORS | API surface | **Low** | Accepted; the `Deny`-all-but-named-roles policy exempts only anonymous `OPTIONS`, and the mock returns headers only | `modules/*_stage/main.tf`, `modules/console_api/main.tf` |
| 10 | WAF absent on the APIs and CloudFront; no cross-region replication of the audit bucket | Edge protection / DR | **Low** | Accepted at course scope (IAM-authed, resource-policy-scoped, single-region); recorded as residual risk | `.checkov.yaml` (justified skips) |
| 11 | No load / DR / chaos testing; cold-start latency unmeasured under load | Performance / resilience | **Low** | Open (follow-on: load + chaos testing, right-size memory/concurrency) | §5.5, §6.5 |

Full raw scan output (checkov / ruff / pip-audit / tflint pass counts): **Appendix A**;
every checkov skip is individually justified in `.checkov.yaml`.

---

## 5. Residual risks

1. **Real-source scope + PII:** one real source (SAM exclusions) is live, capped to a
   demo-sized slice, and contains real public debarment names (DEC-22); the other three
   sources are synthetic. Not the exhaustive federal list; production needs the full
   extract + a vector index.
2. **Semantic eval scope:** measured on a small synthetic set; no adversarial name
   obfuscation, English/Latin names only (§7, `docs/sme/SEMANTIC_EVAL.md`).
3. **Local Terraform state:** safe for one operator, unsafe for a team/CI applies.
4. **Webhook single notification path (DEC-7):** age-of-oldest-message alarm is the only
   backstop.
5. **No load/DR testing;** cold-start latency unmeasured under load.
6. **Bedrock as a soft dependency in B:** an outage silently degrades the semantic net to
   rule-based screening (observable via Bedrock error metrics; alarm is follow-on).

---

## 6. Recommended follow-on work

1. **Full real-source integration:** the async SAM extract + a real vector index
   (OpenSearch) for the complete list; integrate the three restricted sources (SSA DMF,
   TOP, OIG LEIE) with proper record linkage.
2. **Remote Terraform state** + the OIDC plan role so `plan.yml` reflects real drift.
3. **Bedrock-availability alarm** so a silent semantic-net degradation is observable.
4. **Materialized analytics rollup** for production-scale aggregation.
5. **Load & chaos testing;** measure cold-start and right-size memory/concurrency.
6. **Per-source semantic thresholds** tuned on real data (re-run the §7 sweep).
7. **Second notification path** to harden DEC-7 beyond the single webhook.

---

## 7. LLM workflow evaluation (course objective 5)

The Bedrock-embedding semantic matcher in Component B is the one differentiating
component, and it is **measured**, not asserted. On a 27-case labeled synthetic set
(10 true variants, 7 surface-similar hard negatives, 10 clean) scored with real
`amazon.titan-embed-text-v2:0` embeddings, at the deployed 0.72 cosine threshold:
**precision 0.83, recall 1.00, F1 0.91, false-positive rate 0.12, target accuracy 1.00**,
embeddings **deterministic (0.00 drift)**. The threshold sweep confirms 0.72; the two
false positives are near-duplicate distinct entities where routing to a human is
defensible (one intrinsic, contained by the REVIEW cap). Method, per-case data, sweep,
recommendation, and scope limits: `docs/sme/SEMANTIC_EVAL.md`. Reproducible via
`scripts/eval_semantic_matching.py` (real Bedrock) and `tests/test_semantic_eval.py`
(deterministic, no Bedrock).

**Measured cost** (`docs/sme/BEDROCK_COST.md`, us-east-2 rates from the AWS Price List
API 2026-07-06): Titan embeddings ~$0.0000001 each; Nova Lite briefs ~$0.000035 each; a
representative demo run = **$0.00011** total Bedrock cost. Idle-vs-active framing per
DEC-19 (~$2/mo idle vs ~$700/mo for a managed vector DB). **Responsible use:** the brief
is advisory, grounded, and never enters the immutable record (code-verified).

---

## 8. Messy real-data handling (course objective 10)

The live screening list includes the **real GSA SAM.gov exclusions** (DEC-22), ingested
via `scripts/ingest_sam_exclusions.py` and published through the same versioned lifecycle
as the admin console (no second store). Real-world messiness handled and documented in
`docs/sme/REAL_SOURCE_INGEST.md`: SAM has **no TIN** (name-based matching only; UEI kept
for provenance), classification variety (Firm/Individual/Vessel/Special Entity),
exclusion-type variety mapped to severity, active-only filtering, dedupe, schema-drift
tolerance, and a deliberate **size cap** (fits the in-store-cosine budget and the source's
rate limit). Two source paths: the authoritative GSA API (`--source gsa`, key-gated,
10/day free tier) and a keyless bulk mirror (`--source opensanctions`, CC-BY-NC, used for
the live publish). Live result: reference **version 4 = 90 real SAM exclusions + 6
synthetic restricted entries**, verified end to end (§2.2).

---

## 9. AI-assisted development, used with judgment (course objective 2)

PrePayGuard was built with AI-assisted development (Claude Code) under a gated,
human-approved workflow, not free-form generation. AI assistance produced handler
code (A to E, console API), the Terraform modules, the tests, the React console, and
this SME hardening pass. Review and control came from human approval gates at every
version, decisions recorded with their alternatives and objections in
`foundation/DECISIONS.md` (27 locked), and static analysis (ruff, checkov, tflint,
pip-audit) plus the test suite on every change. Judgment was applied, not deferred to
the assistant: examples include rejecting the Powertools idempotency decorator for
visible hand-rolled logic (DEC-13), rejecting an ML risk model for transparent rules
(DEC-14), rejecting a managed vector DB for in-store cosine (DEC-19), and, in this
pass, correcting generated assumptions from live findings (the SAM API 406 header
behavior and nested schema, the 10/day rate limit found via a real 429, and a
normalization bug where the substring "active" matched "Inactive", caught by a test).
Full account: `docs/sme/AI_ASSISTED_DEVELOPMENT.md`.

---

## Appendix A: Raw scan output

```
checkov  : Passed / Failed 0 / Skipped (justified in .checkov.yaml)
ruff     : All checks passed!            (src + tests; config ruff.toml)
pip-audit: No known vulnerabilities found
tflint   : 0 issues
terraform fmt -check / validate: clean
pytest   : 135 passed        vitest: 34 passed
GitHub Actions ci.yml: green
```

*(Original v1.0.0 scan snapshot 2026-07-03: checkov 289/0/3, referenced for the graded
baseline; re-run current at each gate.)*

## Appendix B: Evidence & decisions

- `docs/evidence/live_object_lock_proof.txt`, delete/shorten AccessDenied (PASS)
- `docs/evidence/live_e2e_run.txt`, backend three-payment run
- `docs/evidence/console_live_e2e.txt`, signed-in console flow
- `docs/evidence/live_real_source_ingest.txt`, real SAM name screened end to end
- `docs/sme/`, ORIENTATION, SEMANTIC_EVAL, BEDROCK_COST, REAL_SOURCE_INGEST, DEMO_SCRIPT
- Decisions: `foundation/DECISIONS.md` (27 LOCKED) · Roadmap: `foundation/VERSION_ROADMAP.md`

> Note: `HANDOFF.docx` is the rendered twin of the v1.0.0 body and is now behind this
> refresh; regenerate it from this Markdown before final submission.
