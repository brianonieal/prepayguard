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
on AWS** (us-east-2), console at **https://d2rbxaf6pqgvb1.cloudfront.net**. **29
architectural decisions locked.** Verified green: **pytest `152 passed, 1 xfailed`, console
vitest green, checkov 662/0/3, ruff clean, tflint clean, terraform validate clean.** The one differentiating
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

The same pipeline as a diagram (GitHub renders the block below):

```mermaid
flowchart TD
  caller["caller (SigV4, submitter role — DEC-5)"] --> apigw["API Gateway — AWS_IAM<br/>payee validation: maxLength 35 + printable-ASCII (DEC-29)"]
  apigw --> A["A · Intake<br/>payment-ID idempotency (commitment 1)"]
  A -->|SQS| B["B · Enrichment<br/>TIN/name exact · fuzzy · semantic (Titan)"]
  B -->|SQS| C["C · Risk Scoring<br/>rule score + disposition; NAME_MATCH_CAP=60"]
  C -->|SQS| D["D · Disposition"]
  D --> audit[("S3 Object Lock audit<br/>COMPLIANCE — commitment 4")]
  D --> review["SQS review queue<br/>ambiguous → human (commitment 2)"]
  D --> hook["webhook (Secrets Manager — DEC-7)"]
  refstore[("versioned reference list<br/>S3 + per-entry Titan vectors")] --> B
  E["E · Batch Ingest (S3-triggered)"] -->|reuses A's queue + idempotency (DEC-16)| B
  F["F · Feeder (EventBridge)"] --> E
  G["G · Refresher (EventBridge, daily)"] --> refstore
  console["Reviewer Console (React/CloudFront)<br/>Cognito → SigV4 (DEC-15)"] --> capi["Console API (AWS_IAM)<br/>reviews · audit · decisions · LLM brief (advisory)"]
  capi -.reads.-> audit
  capi -.reads.-> review
  subgraph controls["cross-cutting: every SQS stage has DLQ+redrive (commitment 2), max-concurrency + queue-depth alarm (commitment 3)"]
  end
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
  modeled rather than integrated. OIG LEIE **is** publicly downloadable; keeping it synthetic
  here is a **deliberate scoping choice** (one real end-to-end integration — SAM — is enough to
  demonstrate the ingest/refresh path; a second adds cost and PII surface without new evidence),
  **not an oversight or a missed source.** See §8 and `docs/sme/REAL_SOURCE_INGEST.md`.
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

Runner: **pytest** (hermetic, moto-backed) + console **vitest**. **pytest `152 passed,
1 xfailed`** (the xfail is the documented F1 residual, not a failure), vitest green, both in CI.
**Rendered summary + four-commitment mapping + Object-Lock moto caveat: [`docs/TEST_REPORT.md`](TEST_REPORT.md).**
Registry: `foundation/TESTS.md`.

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
- **Deployment-readiness gotcha (ERR-1, RESOLVED v3.9.0):** `terraform validate` passing does
  **not** guarantee `apply` succeeds. The 2.1e payee-validation model first failed at `apply`
  (`UpdateModel: Invalid model schema specified`) because an HCL `? :` between two differently-
  shaped schema objects unified them to `map(string)` and **stringified the integer `maxLength`**
  (`"35"`), which API Gateway rejects — `validate` does not evaluate the rendered API-Gateway
  schema, so it passed. Fixed by selecting between two independently-`jsonencode`d strings. Lesson
  for future model edits: never `? :` between object shapes if values must keep distinct types.
  Full post-mortem: `foundation/ERRORS.md` ERR-1.

---

## 4. Security findings

Zero failing **static-analysis** findings across checkov (662/0/3), ruff (pass), pip-audit
(8/8 components clean), tflint (clean) — raw dated output in `docs/evidence/scans/` (2026-07-09).
**But static analysis is not the whole picture:** the **container-image** scan (ECR scan-on-push,
the DEC-8 image-scanning mechanism) reports **2 HIGH + 1 MEDIUM + 1 LOW OS-package CVEs on every
image** at the deployed tag — see §4.1 row 12 and `docs/evidence/scans/ecr-image-scan-2026-07-09.txt`.
Posture is otherwise defense-in-depth:

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
- **Supply chain (DEC-8/9):** pip-audit + checkov + tflint + ruff in CI (Python deps clean);
  ECR immutable tags + scan-on-push for images. Grype (DEC-8 original) was superseded by ECR
  scan-on-push (DEC-8 v3.7.2 amendment; hermetic CI can't build/scan images) — Grype the tool
  never ran, and the handoff does not claim it did (`docs/evidence/scans/grype-2026-07-09-superseded.txt`).
  The ECR scan's actual findings (2 HIGH base-image CVEs/image) are now retrieved and rated below.
- **Responsible AI:** the reviewer brief (DEC-20) is advisory only, grounded in the audit
  record, and never written to S3/the audit record/the decision (code-verified,
  `docs/sme/BEDROCK_COST.md` §5). The semantic matcher only ever adds a REVIEW flag.

### 4.1 Risk-rating table (DEC-11)

Findings rated High / Medium / Low by likelihood × impact at course scope. The load-bearing
platform controls (AWS_IAM auth + resource-policy scoping, Object Lock COMPLIANCE immutability
live-verified, SSE-KMS, maker/checker segregation of duties) are in place and evidenced. **Two
High-severity findings are open, both with a stated remediation path:** the matcher-dilution
evasion (row 5, F1 — partly remediated by 2.1e input validation, residual open) and the base-
image OS CVEs surfaced by the ECR scan (row 12). The remaining items are Medium/Low hardening,
observability, and scope.

| # | Finding | Area / component | Severity | Status | Evidence |
|---|---|---|---|---|---|
| 1 | CloudWatch alarms (queue-depth, DLQ-not-empty) have no notification target (`alarm_actions` empty); an operator is not paged when a DLQ fills | Observability / B-C-D, review queue | **Medium** | Open (follow-on: wire an SNS topic). Partial backstop: the review queue's `ApproximateAgeOfOldestMessage` alarm covers the human-review path | `modules/queue_worker_stage/main.tf` (alarms), DEC-19 |
| 2 | Console JS dependencies are not CVE-scanned in CI (`npm ci --no-audit`, no Dependabot); Python side is covered by `pip-audit --strict` | Supply chain / console | **Medium** | Open (follow-on: enable `npm audit` / Dependabot) | `.github/workflows/ci.yml` |
| 3 | Local Terraform state; safe for one operator, unsafe for team/CI applies | Deployment / state | **Medium** | Accepted at course scope; remote state + OIDC plan role is the production upgrade | `environments/dev/backend.tf`, `plan.yml` |
| 4 | One real screening source (SAM exclusions) capped to a demo-sized slice; three sources remain synthetic | Data fidelity / reference list | **Medium** | Accepted / documented; full extract + record linkage is follow-on | DEC-22, `docs/sme/REAL_SOURCE_INGEST.md` |
| 5 | Semantic matcher is defeated by name **dilution** (append ~5 distant tokens / a homoglyph): a listed Do Not Pay entity is auto-approved (F1). The 27-case eval's "recall 1.00" had no append cases; the 62-case set (append-inclusive) shows the append-positive and hard-negative cosine distributions overlap — **no threshold separates them**, and 0.72 already yields 7/16 hard-negative false positives | Model robustness / component B | **High** | **Partly remediated:** 2.1e input validation (DEC-29) narrows it (bounds the field, closes the transliteration class) but leaves 75/96 evadable; windowed matching is the recommended, un-built backstop | `docs/sme/INJECTION_THREAT_MODEL.md`, `docs/evidence/EVAL_REPORT.md`, `docs/sme/SEMANTIC_EVAL.md` §9 |
| 6 | Bedrock is a soft dependency in B; an outage silently degrades the semantic net to rule-based screening | Availability / component B | **Low** | Mitigated: fails safe to deterministic rules (not blind); a Bedrock-availability alarm is follow-on | `src/component_b_enrichment/app.py` (semantic degrade) |
| 7 | Single webhook notification path for review routing (DEC-7) | Review routing / component D | **Low** | Mitigated by the age-of-oldest-message alarm; a second path is follow-on | DEC-7, `modules/review_queue/main.tf` |
| 8 | MFA is optional (opt-in TOTP), not enforced | Identity / Cognito | **Low** | Accepted; operator-provisioned users only, no public sign-up | `modules/console_foundation/main.tf` |
| 9 | `OPTIONS` preflight is unauthenticated (`Principal:"*"`, MOCK integration, no data path) for browser CORS | API surface | **Low** | Accepted; the `Deny`-all-but-named-roles policy exempts only anonymous `OPTIONS`, and the mock returns headers only | `modules/*_stage/main.tf`, `modules/console_api/main.tf` |
| 10 | WAF absent on the APIs and CloudFront; no cross-region replication of the audit bucket | Edge protection / DR | **Low** | Accepted at course scope (IAM-authed, resource-policy-scoped, single-region); recorded as residual risk | `.checkov.yaml` (justified skips) |
| 11 | No load / DR / chaos testing; cold-start latency unmeasured under load | Performance / resilience | **Low** | Open (follow-on: load + chaos testing, right-size memory/concurrency) | §5.5, §6.5 |
| 12 | Every Lambda container image carries **2 HIGH + 1 MEDIUM + 1 LOW** OS-package CVEs from the shared amzn2023 base (`sqlite-libs` CVE-2026-11822/11824 HIGH, `libxml2` MEDIUM, `gnupg2` LOW), surfaced by ECR scan-on-push. Not the app's Python deps (pip-audit clean) | Supply chain / all images | **High** | Open (follow-on: rebuild on a patched base image / `dnf upgrade` in the Dockerfile; clears the two HIGH sqlite CVEs) | `docs/evidence/scans/ecr-image-scan-2026-07-09.txt` |
| 13 | Matcher **false positives** on legitimate look-alike names (F5): 7/16 hard negatives score ≥0.72 on the eval; two (`Initech Solutions LLC`, `Globex Onshore Inc`) at 0.966 are FPs at every threshold below 0.966. Same whole-string defect as F1 (row 5), opposite direction | Model robustness / component B | **Medium** | Contained: `NAME_MATCH_CAP=60` caps a semantic hit to REVIEW (reviewer load, not a wrong auto-reject); robust-matcher follow-on fixes F1 and F5 together | `docs/sme/INJECTION_THREAT_MODEL.md` F5, `docs/evidence/EVAL_REPORT.md` |

Full raw scan output — checkov / ruff / pip-audit / tflint (static) **and** the ECR image-scan
findings — is committed under **`docs/evidence/scans/`** (dated 2026-07-09), summarized in
**Appendix A**; every checkov skip is individually justified in `.checkov.yaml`.

---

## 5. Residual risks

1. **Real-source scope + PII:** one real source (SAM exclusions) is live, capped to a
   demo-sized slice, and contains real public debarment names (DEC-22); the other three
   sources are synthetic. Not the exhaustive federal list; production needs the full
   extract + a vector index.
2. **Matcher dilution / F1 (High, partly remediated):** the semantic + string matcher is
   defeated by appending ~5 distant tokens or a homoglyph to a listed name; the append-positive
   and hard-negative cosine distributions overlap, so no threshold fixes it (0.72 already gives
   7/16 hard-negative false positives on the eval set). 2.1e input validation (DEC-29) narrows
   it but leaves 75/96 of the list evadable and opens a cap-side false-accept on long entities
   (1/11 unscreenable, C4); a windowed matcher is the recommended, un-built backstop. Eval is
   synthetic (same author wrote perturbations + matcher). `INJECTION_THREAT_MODEL.md`,
   `EVAL_REPORT.md`, `SEMANTIC_EVAL.md` §9.
3. **Container base-image CVEs (High):** every Lambda image carries 2 HIGH OS-package CVEs
   (`sqlite-libs`) from the amzn2023 base (ECR scan-on-push, §4.1 row 12); rebuild on a patched
   base to clear. Grype the tool never ran (superseded by ECR scan-on-push, DEC-8 v3.7.2).
4. **Local Terraform state:** safe for one operator, unsafe for a team/CI applies.
5. **Webhook single notification path (DEC-7):** age-of-oldest-message alarm is the only
   backstop.
6. **No load/DR testing;** cold-start latency unmeasured under load.
7. **Bedrock as a soft dependency in B:** an outage silently degrades the semantic net to
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
`foundation/DECISIONS.md` (29 locked), and static analysis (ruff, checkov, tflint,
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

Raw, dated artifacts committed under **`docs/evidence/scans/`** (2026-07-09):

```
STATIC ANALYSIS (as CI runs them)
  checkov  : Passed 662 / Failed 0 / Skipped 3 (justified in .checkov.yaml)   scans/checkov-2026-07-09.txt
  ruff     : All checks passed!  (ruff check src tests)                        scans/ruff-2026-07-09.txt
  pip-audit: No known vulnerabilities found — all 8 src/*/requirements.txt     scans/pip-audit-2026-07-09.txt
  tflint   : 0 issues (--recursive)                                           scans/tflint-2026-07-09.txt
  terraform fmt -check / validate: clean
  pytest   : 152 passed, 1 xfailed        vitest: (console) green
  GitHub Actions ci.yml: green

CONTAINER IMAGE SCAN (ECR scan-on-push — DEC-8 mechanism; Grype the tool NOT run, superseded)
  every image @v3.8.3: 2 HIGH + 1 MEDIUM + 1 LOW                              scans/ecr-image-scan-2026-07-09.txt
    HIGH   sqlite-libs  CVE-2026-11822, CVE-2026-11824
    MEDIUM libxml2      CVE-2026-6653
    LOW    gnupg2       CVE-2026-57062
  Grype status                                                               scans/grype-2026-07-09-superseded.txt
```

*(Original v1.0.0 scan snapshot 2026-07-03: checkov 289/0/3, referenced for the graded
baseline; re-run current at each gate. The 1 xfailed pytest is the documented F1 short-name
append residual — `tests/test_injection_resistance.py`.)*

## Appendix B: Evidence & decisions

- `docs/evidence/live_object_lock_proof.txt`, delete/shorten AccessDenied (PASS)
- `docs/evidence/live_e2e_run.txt`, backend three-payment run
- `docs/evidence/console_live_e2e.txt`, signed-in console flow
- `docs/evidence/live_real_source_ingest.txt`, real SAM name screened end to end
- `docs/sme/`, ORIENTATION, SEMANTIC_EVAL, BEDROCK_COST, REAL_SOURCE_INGEST, DEMO_SCRIPT
- Decisions: `foundation/DECISIONS.md` (27 LOCKED) · Roadmap: `foundation/VERSION_ROADMAP.md`

> Note: `HANDOFF.docx` is the rendered twin of the v1.0.0 body and is now behind this
> refresh; regenerate it from this Markdown before final submission.
