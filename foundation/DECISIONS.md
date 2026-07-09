# DECISIONS.md — PrePayGuard ("Treasury")
# Seeded at foundation build (v0.1.0, 2026-07-03) verbatim from TREASURY_DECISIONS_LOG.md.
# DEC-1..12 seeded verbatim; DEC-13+ added during build. Running total: 29 LOCKED, 0 OPEN.
# Do not re-open a LOCKED decision without a stated reason for the pivot.
# New decisions append below DEC-12 in the same format (DEC-N, severity, decision,
# alternatives considered, rationale, risk acknowledged, resolution, status).

---

## DEC-1 - IaC Tool and Module Structure
**Date:** prior planning session (exact date not available in current context)
**Severity:** FULL
**Decision:** Terraform, using a shared module (queue_worker_stage) for Components B, C, and D via for_each, plus a separate api_intake_stage module for Component A.
**Assumptions tested:** assumed B, C, and D's infrastructure shapes are identical enough (Lambda container image, SQS in, SQS out, DLQ, IAM role, CloudWatch queue-depth alarm) to share one module without hiding real behavioral differences between the stages.
**Alternatives considered:** three independent per-component modules (rejected: three near-identical DLQ and scaling configurations risk drift across a compliance-relevant demo); AWS SAM and AWS CDK (rejected in favor of Terraform as the committed IaC tool in an earlier session; no further comparison recorded here).
**Rationale:** B, C, and D share identical infrastructure shape and differ only in container image, environment variables, memory, and timeout. A for_each-based shared module removes three near-duplicate blocks of HCL and keeps DLQ and scaling settings consistent across all three stages, which directly supports graded commitments 2 and 3. Component A is genuinely different (API Gateway trigger, not SQS-triggered) and gets its own module rather than being forced into the shared one.
**Risk acknowledged:** a shared module can hide real per-stage differences behind generic variables if B, C, or D ever need materially different behavior (for example, a second output target). Watch for this if any stage's needs diverge during implementation.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-2 - Compute Model
**Date:** prior planning session (approved as part of the original project proposal)
**Severity:** FULL
**Decision:** Lambda container images for all four components. No EC2 workers, no zip-based Lambda deployment.
**Alternatives considered:** an EC2-based worker-process architecture existed in a skill file that incorrectly named this project as its reference case. That skill file has been corrected to exclude this project explicitly and no longer describes this architecture as applying here.
**Rationale:** satisfies the containerization requirement within AWS free-tier credits; approved by the professor as part of the original project proposal.
**Risk acknowledged:** container-image Lambdas have higher cold-start latency than zip-based Lambdas. Acceptable here because this is a screening pipeline, not a latency-critical per-transaction system.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-3 - Queue Decoupling and Disposition Logic
**Date:** prior planning session
**Severity:** FULL
**Decision:** SQS between all four components. Clean payments auto-approve, ambiguous payments route to human review, bad payments are rejected.
**Rationale:** mirrors the Treasury Do Not Pay pattern this project is modeled on. Queue decoupling is also the mechanism underlying graded commitments 2 (failure routing) and 3 (queue-depth scaling).
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-4 - Immutable Audit Log
**Date:** prior planning session
**Severity:** FULL
**Decision:** S3 Object Lock in Compliance mode for the audit log, set at bucket creation.
**Alternatives considered:** Amazon QLDB (rejected: retired July 31, 2025).
**Rationale:** satisfies graded commitment 4 (immutability) using a currently supported AWS service.
**Risk acknowledged:** Compliance mode cannot be shortened or removed by any principal, including the account root, once set. The retention period must be chosen correctly before the first write.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-5 - API Authentication on Component A
**Date:** 2026-07-03
**Severity:** FULL
**Decision:** AWS_IAM authorization on the API Gateway method for the Payment Intake API, scoped with a resource policy to a specific IAM role.
**Alternatives considered:** an API key (rejected: demonstrates rate-limiting, not authentication or authorization, and the course's identity objective names both explicitly); Amazon Cognito (rejected: built for end-user login, and Component A is a system-to-system endpoint, not user-facing).
**Rationale:** ties caller identity to a cryptographically verified AWS principal rather than a static header value. Directly answers the course's identity, authentication, and authorization objective, which had no answer at all before this decision.
**Risk acknowledged:** IAM auth requires the caller to sign requests with SigV4, which adds integration work for any test client. Must be accounted for in test setup.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-6 - CI/CD Pipeline
**Date:** 2026-07-03
**Severity:** FULL
**Decision:** GitHub Actions. One workflow runs terraform fmt -check, terraform validate, tflint, and pytest on every push. A second workflow runs terraform plan on pull requests to main and posts the diff as a comment. No auto-apply on merge; terraform apply stays a manual, deliberate action.
**Alternatives considered:** auto-apply on merge (rejected: this is a free-tier-credit-funded graded prototype, and an auto-apply pipeline that misfires can consume credits before anyone notices).
**Rationale:** answers the course's CI/CD objective while keeping cost risk bounded.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-7 - Secrets Management
**Date:** 2026-07-03
**Severity:** FULL
**Decision:** Component D publishes a notification to a webhook (Slack incoming webhook or a generic HTTP endpoint) whenever it routes a payment to human review. The webhook URL is stored in Secrets Manager. Component D's Lambda execution role is granted secretsmanager:GetSecretValue scoped to that one secret ARN only. Components A, B, and C have no secrets and make no external calls.
**Assumptions tested:** the initial candidate (no secret anywhere, Component B reads only a DynamoDB table it owns) was reconsidered against course objectives 7 and 9, both of which name secrets handling and secrets management explicitly. A system with zero secrets satisfies those objectives only through a written justification, not through demonstrated capability, which conflicts with the standing show-don't-assert principle for this build.
**Alternatives considered:** no secret anywhere, with an explicit written statement in the handoff package that this system has no secrets (rejected: satisfies the objective on paper only, not through evidence). Adding a secret to the payment-processing path itself with no functional need (rejected: a credential added only to satisfy a rubric line is poor engineering judgment, and reads worse to a grader than an honest no-secrets statement would have).
**Rationale:** the human-review path had no notification mechanism at all; nothing told a reviewer an item was waiting. That is a real gap in "routes ambiguous to human review," not a contrived one. Fixing it with a webhook happens to require a credential, which gives objectives 7 and 9 an actual demonstrated artifact (a working least-privilege secret retrieval) instead of a non-use justification, while also closing an operational hole in the design.
**Risk acknowledged:** if the webhook endpoint is unreachable or misconfigured, review-queue items could sit unnoticed with no alternative alert path. A fallback check (for example, a scheduled check of review-queue depth) is worth adding if time allows, but is not a blocker for v0.1.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-8 - Dependency and Image Scanning
**Date:** 2026-07-03
**Severity:** LIGHTWEIGHT
**Decision:** pip-audit against each component's requirements.txt; Grype against each built ECR image. Both run in CI (see DEC-6).
**Rationale:** answers the course's vulnerable-package and dependency-security objective. Reuses a tool (Grype) already used successfully in this program's prior security labs.
**Amendment (v3.7.2, 2026-07-07):** the CI in `.github/workflows/ci.yml` is deliberately hermetic (DEC-6: no AWS credentials, no image build in CI), so container images are not built there and Grype cannot scan them in-pipeline. Image scanning is instead provided by **ECR scan-on-push** (`modules/ecr_repo/main.tf`, `scan_on_push = true`) on every pushed image, and JS dependencies gained a blocking `npm audit --omit=dev --audit-level=high` gate plus Dependabot. Net posture is unchanged (pip-audit for Python packages, ECR scan for images, npm audit for JS), but the mechanism differs from the original "Grype in CI" wording; running Grype in a credentialed deploy workflow is recorded as optional follow-on.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-9 - Static Analysis
**Date:** 2026-07-03
**Severity:** LIGHTWEIGHT
**Decision:** tflint and checkov on the Terraform; ruff on the four Lambda handlers. Runs in the same CI workflow as DEC-6.
**Rationale:** checkov specifically catches Object Lock misconfiguration, which is the exact class of mistake that would silently fail graded commitment 4.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-10 - Rollback Mechanism
**Date:** 2026-07-03
**Severity:** LIGHTWEIGHT
**Decision:** Lambda versioning and aliases. Each deploy publishes a new version; the alias points to it; rollback repoints the alias to the prior version.
**Alternatives considered:** full terraform apply/destroy as a rollback method (rejected: too coarse and slow to count as a real rollback plan for a graded deliverable).
**Rationale:** answers the course's rollback-planning objective with one mechanism that is identical across all four components, documented once in ARCHITECTURE.md rather than repeated per component.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-11 - Capstone Handoff Package Format
**Date:** 2026-07-03
**Severity:** FULL
**Decision:** single deliverable, produced in both a rendered document (Word or PDF) and the underlying Markdown or repo docs. No page limit. The package is the entire deliverable; no separate live demo or presentation is implied beyond it. Audience is the course instructors, who want to see a working app with full documentation, not a simplified non-technical summary. Six required sections, matching the syllabus exactly: architecture notes, tests, deployment documentation, security findings, residual risks, recommended follow-on work.

Section-level detail:
- Tests: requires a rendered report, not just test files sitting in the repo.
- Security findings: requires actual scan output (from DEC-8 and DEC-9), referenced in an appendix, with a narrative summary and a risk-rating table (High/Medium/Low, finding, affected component, remediation status) in the main body.
- Architecture, failure modes, and known unknowns (course objective 3): written forward-looking, as the system's own designer documenting its failure modes and untested paths. Not backward-framed as if discovering an inherited system.
- Residual risks and follow-on work: scoped generally, not restricted only to the specific gaps closed during this planning phase.

**Rationale:** settled directly with Brian. The forward-looking framing choice on objective 3 specifically rejects backward-discovery framing because Brian did not inherit this system, and writing it as a discovery narrative would misrepresent the actual approval basis for the project.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-12 - Project and Course Identity
**Date:** confirmed 2026-07-03 (originally approved in an earlier, undated planning session)
**Severity:** FULL
**Decision:** PrePayGuard, referenced as "Treasury," is the capstone project for the JHU Certificate in AI Engineering, course CO.EN.AIE.LLL.2026.01. Confirmed directly by Brian's professor.
**Alternatives considered:** none. This was raised as a possible mismatch against the AI Engineering syllabus's generic "inherited legacy system" framing, and resolved by direct professor confirmation, not by argument.
**Rationale:** professor confirmation is authoritative and overrides generic syllabus language, which was written for a different default project shape than the one actually assigned and approved here.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-13 - Idempotency Backing Store (Component A)
**Date:** 2026-07-03
**Severity:** FULL
**Decision:** DynamoDB single-item conditional write (`PutItem` with `ConditionExpression attribute_not_exists(payment_id)`) as Component A's idempotency store for graded commitment 1, with an explicit **PENDING → SENT status field** and **original-result replay**: on a duplicate, the handler reads the stored item and returns the original disposition + queue-message-id rather than rejecting. Ordering is write-PENDING → SendMessage to the output queue → update-to-SENT; the fast-path replay fires only on SENT, and a duplicate landing on a PENDING item re-drives the send (covering a crash between the two writes). Hand-rolled (mechanism visible in `app.py`), not the Lambda Powertools utility. The table lives inside the `api_intake_stage` module (single consumer). Provisioned free-tier capacity; a TTL attribute treats the table as a short-lived dedup cache while Component D's S3 Object Lock write remains the canonical audit record.
**Assumptions tested:** that "idempotency" (commitment 1) means replay-returns-original-result, not dedup-by-rejection; and that the two-phase (DynamoDB + SQS) write has no silent-loss window.
**Alternatives considered:**
- SQS FIFO content-based dedup — rejected earlier (5-minute window is not durable payment idempotency; constrains throughput/ordering).
- S3 conditional PutObject (If-None-Match) — rejected: the only in-design bucket is D's Object Lock Compliance audit store (spoken for by DEC-4); a second bucket for dedup adds IAM + lifecycle to save nothing over DynamoDB and loses cheap read-back by payment_id.
- AWS Lambda Powertools idempotency utility — viable and correct-by-construction (closes both HIGH objections automatically), but hides the mechanism behind a decorator. Rejected in favor of visible hand-rolled logic because commitment 1's deliverable is *demonstrating* idempotency; reversible if the professor prefers managed tooling.
**Critical-thinker objections raised & resolution:**
- HIGH — "reject ≠ idempotent": resolved by storing disposition + queue-message-id and replaying the original result on a duplicate.
- HIGH — two-phase silent payment loss (item exists, SQS send never happened, retries then blocked; Component A has no DLQ): resolved by the PENDING→SENT status field with re-drive on a PENDING hit.
- MEDIUM — billing mode: resolved to provisioned (25 RCU / 25 WCU, free-tier), not on-demand (not free-tier-covered).
- MEDIUM — TTL vs. audit retention (DEC-4): resolved by documenting the table as a dedup cache and S3 Object Lock as the canonical audit record (one line added to ARCHITECTURE.md at build).
- LOW — server-side conditional-write atomicity is a *strength*: foregrounded as commitment-1 evidence (the test asserts exactly-one-wins under concurrent identical payment_ids).
- Module placement: inside `api_intake_stage` (single-instance module; PAT-T1's for_each sibling-reference concern does not apply).
- Encryption: AWS-managed at-rest by default; a customer-managed KMS key only if checkov (CKV_AWS_119) requires it and cost permits — resolved against the scanner at build.
**Rationale:** DynamoDB's conditional write is the platform-correct atomic primitive for payment-ID dedup and is strongly consistent under concurrent duplicates — the single most gradeable fact for commitment 1. Hand-rolling the surrounding PENDING→SENT state machine keeps the mechanism visible for a show-don't-assert rubric, and the adversarial tests (concurrent race, crash-between-writes) convert the hand-roll's correctness risk into evidence.
**Risk acknowledged:** hand-rolled correctness primitives can carry subtle runtime bugs (v0.1.0 reflexion lesson). Mitigated by writing the race and crash-gap tests first, so the two failure modes the critique found are proven closed before the gate closes.
**Confidence:** HIGH (mechanism). **Reversibility:** HIGH — one handler + one table + a few IAM lines; swapping to Powertools later is contained.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-14 - Screening Domain Model (Components B & C)
**Date:** 2026-07-03
**Severity:** FULL
**Decision:** Component B (Enrichment & Reference-Match) matches each payment against a BUNDLED SYNTHETIC reference list (JSON shipped in the image) modeling the real Do Not Pay sources — SSA Death Master File, SAM.gov exclusions, Treasury Offset Program, OIG LEIE — with obviously-fake entries. Matching is deterministic (normalized TIN → confidence 95; exact normalized name → 80) plus light fuzzy (difflib ratio ≥ 0.9 → 60); each match carries source + severity. Component C (Risk-Scoring & Decision Engine) applies a transparent RULE-BASED score to the match set and emits a three-way disposition: TIN match → `reject` (strong identity match), name match → `review` (a *potential* match — false-positive-prone, so it routes to a human), no match → `approve`. The SQS message grows across hops: payment → +`enrichment` → +`risk{score,disposition,reasons}`.
**Alternatives considered:**
- Reference data in DynamoDB or S3 (rejected FOR THIS GATE: adds infrastructure + a `terraform apply`; a bundled list keeps v0.3.0 testable and apply-free. Real data-source integration is clean follow-on work — the swap doesn't touch the SQS plumbing).
- ML / statistical risk model (rejected: opaque, not gradeable as "show the mechanism," and overkill — the real DNP pattern is match/rule-based, not learned).
- Auto-reject on ANY match (rejected: name matches are potential and false-positive-prone; the real program adjudicates them via human review, which is precisely graded commitment 2's rationale — auto-rejecting them would misrepresent the pattern and defeat the human-review path).
**Rationale:** faithful to the real Do Not Pay pattern (match against reference sources; three-way pay/review/reject) while remaining fully demonstrable in a capstone without real PII feeds. The rule-based score keeps the mechanism visible for grading (same show-don't-assert logic as DEC-13). Name-match → review wires commitment 2's human-review path to a real cause rather than a contrived one.
**Risk acknowledged:** a bundled synthetic list is a simulation, not a production data integration — documented as such with an explicit fidelity note for the handoff package. The fuzzy threshold (0.9) is a tunable heuristic. (A domain-fidelity cross-check workflow was started but stopped early for token efficiency; the design stands on best-judgment fidelity to the public DNP pattern.)
**Confidence:** HIGH (structure). **Reversibility:** HIGH — swap the bundled list for a DynamoDB/S3-backed source without touching the handler↔queue wiring.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-15 - Console Auth & Request Signing (Phase 2)
**Date:** 2026-07-04
**Severity:** FULL
**Decision:** The Treasury Console authenticates humans with **aws-amplify** (Cognito User Pool SRP login → Cognito Identity Pool → temporary IAM credentials) and SigV4-signs every API-Gateway request with **aws4fetch**. This REUSES the DEC-5 IAM-auth mechanism for the human surface: the console authenticated role is a second named principal on the intake API's resource policy and the sole principal on the console API. `USER_PASSWORD_AUTH` is enabled on the app client alongside SRP so headless/e2e clients can authenticate (SRP remains the browser default).
**Alternatives considered:** a Cognito authorizer on API Gateway (rejected — bolts a second auth scheme onto the IAM-authed APIs; Identity-Pool→IAM-creds reuses DEC-5 cleanly and keeps every API uniformly AWS_IAM). A backend-for-frontend signer (rejected — an extra hop/service; browser-side SigV4 with short-lived creds is the standard pattern).
**Rationale:** one consistent auth model (AWS_IAM/SigV4) across machine and human callers; short-lived federated creds; no new authorizer surface. Proven live end-to-end (docs/evidence/console_live_e2e.txt): login → temp creds → SigV4 submit → review → decision, all 200.
**Risk acknowledged:** `USER_PASSWORD_AUTH` sends the password to Cognito directly (vs SRP's zero-knowledge proof) — acceptable over TLS here; droppable to SRP-only anytime. The client-side integrity-verify requires JS canonical JSON to match Python's; the live demo uses integer amounts so serialization is identical (float/unicode canonicalization is v1.5.0 hardening).
**Confidence:** HIGH. **Reversibility:** HIGH (auth is a swappable lib seam).
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-16 - Batch Ingestion Reuses the Intake Idempotency Store (v1.6.0)
**Date:** 2026-07-04
**Severity:** FULL
**Decision:** Component E (S3-triggered batch CSV ingestion) enqueues to the **same intake SQS queue** and claims against the **same DynamoDB idempotency table** as Component A, rather than calling the intake API per row or maintaining its own dedup store. E mirrors A's `attribute_not_exists` PENDING->SENT claim inline (against the shared table), batched via `SendMessageBatch`. Result: a payment submitted via BOTH a batch file and the single API dedupes to one screening. E adds intra-file dedup (a `seen` set) because within one file the first occurrence is still PENDING, not SENT, when a repeat is checked.
**Alternatives considered:** (A-per-row) Component E signs and calls `POST /payments` per row — single enforcement path, but chatty (N HTTP round-trips), needs a service-role SigV4 signer, and couples batch throughput to API Gateway limits. (Own store) E keeps a separate idempotency table — simplest to build, but a payment in both paths would screen twice, breaking the "screened once" guarantee. (Shared code library) extract A's claim into a package both images import — cleanest in theory, but the container-per-component build (DEC-2) has no shared build context; a Lambda layer or restructured build is disproportionate for ~15 lines.
**Rationale:** correctness (cross-path idempotency) is the whole point of the intake dedup (commitment 1); the store, not the code, is the source of truth, so sharing the store is what matters. Reuses A's queue + table with no new dedup surface. A cross-path idempotency test and an intra-file dedup test guard the mirrored logic against drift; both verified live (summary queued=2/duplicate=1 on a file with a repeated id).
**Risk acknowledged:** the claim logic is duplicated (not shared) across A and E, so a change to the state machine must land in both — pinned by tests. Component E is a single Lambda parsing a whole file (15-min / memory ceiling); very large files would need sharding (Step Functions) — noted as follow-on, out of v1.6.0 scope.
**Confidence:** HIGH. **Reversibility:** MEDIUM — moving to a shared library or per-row API calls later is contained to Component E; the shared table/queue contract stays.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-17 - Console Roles & Segregation of Duties (v2.0.0)
**Date:** 2026-07-04
**Severity:** FULL
**Decision:** Console access is role-based via Cognito User-Pool GROUPS (submitter / reviewer / admin) mapped to per-group IAM roles through the Identity Pool's Token role-mapping (cognito:preferred_role). API authorization is at the edge (resource policies): reviewer+admin get every route; submitter is scoped to the batch-upload routes only; all three may submit. The maker/checker control IAM cannot express - an approver cannot decide a payment they submitted - is enforced in the handler: Component A stamps submitted_by (cognitoIdentityId), Component D carries it to the reviews table, and console_api's _apply_decision returns 403 when decider == submitted_by (single + bulk).
**Alternatives considered:** a single Cognito authorizer on API Gateway (rejected - bolts a second auth scheme onto the IAM-authed APIs; groups->IAM-roles reuses DEC-5/DEC-15 uniformly). Rules-based role mapping (rejected for Token/preferred_role - precedence lives on the group, simpler). IAM-only SoD (impossible - "not your own payment" is per-item app state, not policy-expressible). Exempting admin from SoD (rejected - SoD is identity-based and absolute; admins are bound too).
**Rationale:** one auth model (AWS_IAM/SigV4) across machine + human callers, now role-scoped; segregation of duties is a core payment-integrity control. Proven live: brian (admin via Token mapping) self-approve -> 403 segregation_of_duties; a different submitter's payment -> 200.
**Risk acknowledged:** SoD identity = cognitoIdentityId, so a non-Cognito submitter (the payment-submitter IAM machine role) has no per-user id and its submissions are approvable by any reviewer - acceptable (a machine test client, not a human maker). Submitter-on-batch authorization is duplicated in the resource policy AND the identity policy (defense in depth); both must stay in sync.
**Confidence:** HIGH. **Reversibility:** MEDIUM - roles/groups are additive; removing SoD is a one-line handler change.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-18 - Reference-Data Lifecycle: Versioned S3 Document (v2.1.0)
**Date:** 2026-07-04
**Severity:** FULL
**Decision:** The Do Not Pay screening lists live in a dedicated versioned S3 store, not in Component B's container image: `reference/current.json` (active pointer, fetched by B with a 60s warm-cache TTL) plus immutable `reference/versions/{N}.json` history. Each doc carries `{version, updated_at, updated_by, sources, entries}`. B stamps `reference_version` on the enrichment block and D writes it into the audit record's provenance - every screening cites the exact list version it matched. Publishing is admin-only (edge Deny on the reviewer role for `PUT /reference` + an ADMIN_ROLE_NAME check in the handler), validates entries, and claims the next version number with an S3 conditional put (`If-None-Match: *`) so concurrent publishes cannot mint the same version. Terraform owns the bucket, never the documents; version 1 is seeded out-of-band from the bundled list. Failure posture in B: S3 error with a warm cache serves the cached copy; with no cache it raises into the retry/DLQ path - never screen against unknown data.
**Alternatives considered:** DynamoDB rows per entry (rejected - versioning a whole-list snapshot in item-per-entry form is clunky; B needs the full list per screening anyway, and a single JSON doc is the natural substrate for v2.2.0 per-entry embeddings). S3 native VersionIds as the citation (rejected - opaque strings; a monotonic integer is human-readable in audit records and trivially resolvable). Terraform-managed seed object (rejected - Terraform would fight the admin publish path; exact lesson of the v1.4.0 SPA index.html drift).
**Rationale:** the citation requirement ("what list said so?") demands immutable, resolvable history; a versioned document store delivers it in ~one page of handler code. Proven live: published v2, screened a payment against a v2-only entry, audit record cites reference_list_version=2, v1 history intact, reviewer publish 403.
**Risk acknowledged:** B's 60s TTL means a publish takes up to a minute to reach warm containers - acceptable for list updates (documented in the admin UI). The stale-cache-on-S3-error fallback favors availability over freshness for up to one container lifetime; flagged for the v2.4.0 analytics/alarm follow-on. Entry validation is structural (name/tin/source/severity), not semantic - garbage names still publish; the human admin is the control.
**Confidence:** HIGH. **Reversibility:** HIGH - the store is read through one function in B and one module in the console; swapping backends never touches the pipeline shape.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-19 - Semantic Payee Matching: Cosine-in-Store (v2.2.0)
**Date:** 2026-07-04
**Severity:** FULL
**Decision:** Semantic payee matching uses Bedrock Titan Embed Text v2 embeddings with **cosine similarity "in the store"** - per-entry vectors are computed at publish time by console_api and stored IN the versioned reference document, NOT in a vector database. Component B embeds the payee ONLY when the deterministic string rules (exact/fuzzy) found nothing, computes cosine in-memory against the stored entry vectors, and adds a `name_semantic` match when the best similarity >= threshold (default 0.72, stored in and versioned with the doc). Semantic matches are capped to REVIEW by Component C (never auto-reject). A Bedrock failure in B degrades to rule-based screening (the deterministic rules already ran) rather than DLQ-ing the payment. Because embeddings are versioned with the list, a screening's cited reference_list_version pins the exact vectors it was judged against.
**Alternatives considered:** OpenSearch Serverless / a managed vector DB (rejected - ~$700/mo always-on minimum vs the ~$2/mo idle baseline [[treasury-cost-posture]], for a reference list of tens-to-hundreds of entries where in-memory cosine over unit vectors is trivially fast). Embedding reference entries in B on cold start (rejected - re-embeds the whole list per cold start, unversioned, unauditable; publish-time embedding computes once and versions with the list). Embedding EVERY payee (rejected - run semantic only when string matching missed, bounding Bedrock calls to the ambiguous cases). Auto-reject on high semantic similarity (rejected - semantic is inherently approximate; a name match however close is never a definitive identity match, only a confirmed TIN rejects, per the decision model).
**Rationale:** catches real-world payee variants (Offshore->Overseas, Inc->Incorporated, suffix swaps) that exact+fuzzy string matching misses, with near-zero cost/latency and full auditability. Proven live: "Globex Overseas Incorporated" (difflib 0.55 to the listed "Globex Offshore Inc" - string-missed) flagged via name_semantic at cosine 0.857, routed to review, audit cites list v3. Empirical separation was clean: clean vendors ~0.24, true variants 0.86-0.97; 0.72 splits them with margin.
**Risk acknowledged:** (1) A Bedrock outage silently disables the semantic net (screening degrades to rules) - a control that can quietly weaken; observable via Bedrock error metrics, alarm is a follow-on. (2) Publish latency scales with entry count (N sequential embed calls in one API request) - fine for tens-hundreds; a large list needs async/batch embedding. (3) One global cosine threshold (0.72) tuned on a small sample; a larger/real list may need per-source tuning. Posture: start conservative, measure, tighten.
**Confidence:** HIGH. **Reversibility:** HIGH - swap cosine-in-store for OpenSearch behind B's `_semantic_match` + console_api's embed-on-publish; the pipeline shape never changes.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-20 - Advisory LLM Adjudication Brief (v2.3.0)
**Date:** 2026-07-04
**Severity:** FULL
**Decision:** Reviewer briefs are generated ON-DEMAND (`GET /reviews/{id}/brief`), READ-ONLY from the audit record, via Bedrock `amazon.nova-lite-v1:0` through the Converse API, and grounded ONLY in that record's evidence. The brief is **never written to S3, the audit record, or the decision**, and never influences scoring - it accelerates human review; the human makes and owns the decision. It is labeled "AI-generated, advisory, not part of the audit record" in the UI. A Bedrock error returns a graceful 502 (the brief is optional; the case is fully reviewable without it). No caching in v0.1 (human-click volume, ~$0.0001/brief on Nova Lite).
**Alternatives considered:** precompute at disposition (Component D) and store the brief (rejected - writes LLM output into the audit path, muddying the advisory boundary, and generates briefs for payments no human ever reviews). Auto-generate on case open (rejected for v0.1 - a reviewer-triggered button is cost-controlled and makes the on-demand/advisory nature explicit). Caching in a briefs table / the reviews item (deferred - negligible cost at click volume; add if usage grows). Claude / Titan Text (Nova Lite chosen - the only text model with access enabled on the account; the Converse API keeps it a one-line swap).
**Rationale:** speed adjudication with a grounded plain-English summary while keeping the immutable record purely evidence-based and the decision purely human. Proven live: the brief for a flagged "Acme Shell LLC" payment cited the SAM-exclusions exact-name match (severity high, confidence 80), the risk score 60, and recommended INVESTIGATE; a follow-up confirmed the audit record has no brief field and the brief prose never entered it.
**Risk acknowledged:** (1) LLM hallucination - mitigated by hard grounding ("reason ONLY from the provided record"), low temperature, the human as decision-maker, and the brief never entering the record; residual risk is a misleading brief, bounded because it is advisory only. (2) No cache -> repeat opens re-invoke (negligible cost; follow-on). (3) Availability - brief unavailable on a Bedrock error, degrading to "no brief".
**Confidence:** HIGH. **Reversibility:** HIGH - one read-only endpoint + one UI panel; removable without touching the pipeline or the audit.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-21 - Analytics Data Model & Read-Only Auditor Role (v2.4.0)
**Date:** 2026-07-04
**Severity:** FULL
**Decision:** Analytics/compliance reporting aggregates over the **audit_index** table (one row per EVERY disposition since v1.5.0) for throughput / disposition mix / hit rate, plus the **reviews** table for queue metrics + reviewer productivity - scan-based aggregation on demand. A new read-only **auditor** Cognito group -> IAM role provides compliance segregation: admitted at the edge on the console API's **GET routes only** (method-scoped resource policy `*/GET/*` + a GET-only identity policy), and `GET /analytics` + `GET /audit-log` are app-gated to **admin+auditor** (reviewer/submitter 403). The auditor can view analytics, the audit log, cases, evidence, and briefs, but can never decide, publish, submit, or upload. CSV export of the audit log is client-side.
**Alternatives considered:** gate analytics to admin-only (rejected - the roadmap and compliance realism call for a segregated read-only oversight persona distinct from the acting roles; separation of oversight from action is the point). A materialized/precomputed analytics table updated by Component D (deferred - a scan is trivially fast at course scale; add a rollup when volume grows). A dedicated analytics store / Athena over the audit S3 (over-engineered for this scale). Per-method resource-policy scoping proved the clean way to make "auditor = read-only" enforceable at the edge, reusing the v2.0.0 role machinery.
**Rationale:** leadership + auditor oversight (throughput, hit rate, disposition mix, queue aging, reviewer productivity) and an auditor export over the immutable audit log, with the compliance-correct read-only persona. Proven live: 178 payments screened, 23.6% hit rate; admin+auditor see analytics, the auditor's decision attempt 403s, the reviewer's analytics 403s.
**Risk acknowledged:** (1) scan-based aggregation is O(table) - fine to low thousands, but a full scan per analytics load will not scale to production volumes; a materialized rollup is the flagged follow-on. (2) reviewer_productivity keys on the decider's cognitoIdentityId (opaque) - human-readable names need a user directory. (3) audit-log returns the latest N (cap 500); a full compliance export at scale needs pagination/streaming.
**Confidence:** HIGH. **Reversibility:** HIGH - analytics is read-only endpoints; the auditor role is additive.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-22 - Wire One Real Reference Source: SAM.gov Exclusions (SME hardening, WO2)
**Date:** 2026-07-06
**Severity:** FULL
**Decision:** Extend DEC-14's bundled-synthetic model by wiring ONE real Do Not Pay source, the GSA SAM.gov exclusions (federal debarment/suspension list), into the SAME versioned reference store (DEC-18), keeping the other three sources (SSA Death Master File, Treasury Offset Program, OIG LEIE) synthetic and clearly labeled. Ingestion is `scripts/ingest_sam_exclusions.py`: it pulls active exclusions from the SAM Exclusions API v4 (`https://api.sam.gov/entity-information/v4/exclusions`, key from `SAM_API_KEY`, never committed), normalizes each record to the reference schema, and publishes a new version through the existing versioned-list lifecycle (conditional put on `reference/versions/{N}.json`, repoint `current.json`) - not a second store. SAM keys on entity name / UEI and carries NO TIN, so the real entries match on the name paths only (exact, fuzzy, semantic); the TIN path never fires for them and the UEI is kept for audit provenance. The real list is ingested at ALL classifications including Individuals (Brian's call), and is size-capped (default 90 most-recent active, sized to fit BOTH the DEC-19 in-store cosine budget and the free key's 10-requests/day limit; a --extract one-call mode or a higher-tier key lifts the cap) so the embedding cost, document size, and API call budget all stay bounded.
**Alternatives considered:**
- Keep all four sources synthetic (rejected: the demo reads as plumbing to an audience that screens the real sources daily; wiring one real source is high executive payoff, objective 10 evidence).
- OpenSanctions `us_sam_exclusions` keyless daily JSON (rejected in favor of the authoritative GSA primary source per Brian's choice; OpenSanctions is CC-BY-NC and a re-publisher. Kept documented as a fallback in REAL_SOURCE_INGEST.md).
- Entity/firm records only, filtering out individuals to stay closest to the repo's PII-avoidance stance (rejected: Brian chose the full list; federal debarment names are public by statute, published expressly so payers can screen).
- Ingest the full ~100k-record extract with per-entry embeddings (rejected: breaks the DEC-19 in-store cosine cost/size assumption and would make thousands of publish-time Titan calls; the documented size cap is the messy-data-handling response, objective 10).
**Rationale:** moves the live demo from "models the structure of the Do Not Pay sources" to "screens against the actual federal debarment list" for one source, while preserving the synthetic-data discipline for the three genuinely restricted feeds. Reuses the DEC-18 lifecycle and the DEC-19 semantic path unchanged, so the audit citation (`reference_list_version`) works end to end for real-source screenings.
**Risk acknowledged:** (1) The real list contains real entity and individual names (public debarment data, some records carry masked PII in the source). This is a deliberate reversal of the "never real PII" posture for THIS one public, screen-intended source; DEC-14 still governs the three synthetic sources. (2) The size cap means the live list is NOT the exhaustive federal list; production would use the async extract endpoint plus a real vector index (DEC-19's OpenSearch swap) rather than in-store cosine. (3) A SAM.gov API key is an external dependency and a rate-limited credential; it belongs in Secrets Manager in production, mirrored on the DEC-7 discipline. (4) SAM has no TIN, so a name-variant of a listed individual only catches via fuzzy/semantic, not the strong TIN path.
**Confidence:** HIGH (mechanism reuses proven lifecycle). **Reversibility:** HIGH - the store is versioned; rolling back is repointing `current.json` to the prior version, and the three synthetic sources are untouched.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-23 - Automated Real-Data Feed: Scheduled Feeder (Component F, v3.3.0)
**Date:** 2026-07-06
**Severity:** FULL
**Decision:** Add a new Lambda **Component F (feeder)**, a container image (DEC-2), invoked by an **EventBridge scheduled rule** (hourly). Each run pulls up to `FEED_LIMIT` (default 10) recent real awards from the public, keyless **USAspending API** (`/api/v2/search/spending_by_award/`), maps each to a payment row (`payee` = Recipient Name, `amount` = Award Amount, no TIN, `payment_id` = deterministic `USASPEND-{Award ID}`), and writes ONE JSON file to the batch-imports bucket under `batch-imports/feed-{ts}/payments.json`. **Component E's existing S3 trigger (DEC-16) ingests it and the whole pipeline screens every row** - no new screening path, no console upload. The scheduled feed is 100% real data; a manual invoke with `{"demo_positive": true}` instead writes ONE clearly-labeled test payment (`payment_id` prefixed `DEMO-POS-`) to a name already on the live Do Not Pay list (default "Globex Overseas Incorporated"), so the flag/review/semantic path is demonstrable on demand WITHOUT contaminating the real feed. A `feeder_enabled` tfvar (default true) toggles the EventBridge rule as a stop switch.
**Alternatives considered:**
- Poll for "real-time" data (rejected: public federal data publishes on a lag; there is no real-time payment stream, so honest framing is automated PERIODIC ingestion, not real-time).
- Automate the reviewer decision to remove the human (rejected: clean payments already auto-approve with zero humans; only potential-match payments route to a person, which is a deliberate control [commitment 2, DEC-14] and the core Do Not Pay pattern - removing it would misrepresent the domain).
- A new screening path / second queue for the feed (rejected: writing to the batch bucket reuses Component E and the entire existing pipeline unchanged; a deterministic payment_id makes overlapping pulls dedupe on the shared idempotency table).
- Blend synthetic positives into the scheduled feed for demo liveliness (rejected: muddies the "is this real data?" credibility; a separate, explicitly-labeled manual demo-positive path keeps the real feed honest while still demonstrating flags).
- Static creds / a secret for the source (rejected/unnecessary: USAspending is public and keyless, so the feeder holds no secret - unlike DEC-7's webhook - and its IAM is just `s3:PutObject` on the feed prefix + logs + xray).
**Rationale:** removes the manual-upload friction so real federal payees flow into the console continuously, while reusing the proven batch path (DEC-16) and keeping the human control (DEC-14) and the honesty posture intact. Verified locally green (pytest 115/115, checkov 569/0, tflint/validate clean) before deploy.
**Risk acknowledged:** (1) Every screened payment writes a PERMANENT S3 Object Lock audit record (DEC-4). The feed is volume-capped (`FEED_LIMIT`) and targets the dev audit bucket (1-day retention, records expire), with the `feeder_enabled` stop switch; it must NOT point at a long-retention COMPLIANCE bucket - flagged. (2) External dependency on USAspending: the feeder logs and skips a run on any API error, never raising, so a bad upstream hour cannot error-spam the schedule. (3) Non-VPC Lambda with outbound HTTPS to a public gov API (documented; acceptable for a keyless public read). (4) Cost scales with the cap (~pennies/day at hourly x 10).
**Confidence:** HIGH. **Reversibility:** HIGH - set `feeder_enabled=false` to stop the feed, or `terraform destroy -target=module.feeder`; nothing is Object-Lock and no existing resource is modified.
**Amendment (2026-07-06, deploy):** the schedule was moved from a 24/7 classic EventBridge rule (`rate(1 hour)`, UTC-only) to **EventBridge Scheduler** (`aws_scheduler_schedule`) running **business hours Eastern, all 7 days** (`cron(0 9-17 * * ? *)` in `America/New_York`), so the window auto-tracks the EST/EDT DST shift instead of drifting an hour in winter. This adds a dedicated scheduler IAM role (invoke the feeder alias only); the `feeder_enabled` stop switch and everything else are unchanged. CKV_AWS_297 (Scheduler CMK) is a justified skip in `.checkov.yaml` (the schedule carries no payload/secret). Live-verified deployed and screening real payees end to end (`docs/evidence/live_feeder.txt`).
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-24 - Automated Reference-List Refresh: Scheduled Refresher (Component G, v3.4.0)
**Date:** 2026-07-06
**Severity:** FULL
**Decision:** Add a new Lambda **Component G (refresher)**, a container image (DEC-2), invoked by an **EventBridge Scheduler** schedule **daily** (`cron(0 6 * * ? *)` in `America/New_York`). Each run re-pulls the real SAM.gov exclusions (keyless OpenSanctions mirror, the same source as the v4 publish, DEC-22), re-embeds them with Titan (DEC-19), and republishes a NEW versioned reference document through the existing versioned-store lifecycle (DEC-18) - but ONLY when the SAM list actually changed (compared on the set of normalized name + UEI keys), so an unchanged day does not churn the version or spend embedding cost. The three synthetic restricted sources (SSA DMF, TOP, OIG LEIE) are carried verbatim with their existing embeddings. A `refresher_enabled` tfvar (default true) toggles the schedule as a stop switch. Least-privilege IAM: read/write the reference bucket's `reference/*` prefix + `bedrock:InvokeModel` on the one embed-model ARN + logs/xray; no secret (public source), no queue.
**Alternatives considered:**
- Leave the SAM list as a one-time snapshot (rejected: the whole point is "the data on PrePayGuard automatically"; a static list goes stale as SAM publishes daily).
- Republish every run unconditionally (rejected: churns the version number and re-embeds daily for no change; the change-detection guard skips unchanged days).
- Fold the refresh into the Component F feeder (rejected: different concern and different IAM - the feeder writes the batch bucket only, the refresher needs reference-bucket read/write + Bedrock; a separate component keeps each least-privilege).
- The authoritative SAM.gov public extract instead of the OpenSanctions mirror (viable follow-on; OpenSanctions is the same GSA data, keyless and already proven in DEC-22, so it is reused for consistency; a swap is contained to `_fetch_sam`).
**Rationale:** completes "the data automatically on PrePayGuard" on BOTH sides - Component F keeps the payments current, Component G keeps the Do Not Pay watchlist current - reusing the DEC-18 versioned lifecycle and DEC-19 in-store cosine unchanged. Honest note preserved: even with a current list, real payees rarely match (that is debarment working); the refresh is about currency, not manufacturing flags.
**Risk acknowledged:** (1) External dependency on the OpenSanctions/SAM feed: the refresher logs and keeps the current version on any fetch error, never raising. (2) Publish latency scales with the entry count (N sequential Titan embeds); capped at REFRESH_LIMIT (90) for the in-store-cosine budget (DEC-19), same cap as the v4 publish. (3) Each real change mints a new immutable versions/{N}.json; version numbers grow over time (expected, human-readable history). (4) CKV_AWS_297 (Scheduler CMK) is a justified skip (the schedule carries no payload/secret).
**Confidence:** HIGH. **Reversibility:** HIGH - set `refresher_enabled=false` to stop refreshes, or `terraform destroy -target=module.refresher`; the reference store and its history are untouched, and any version can be restored by repointing current.json.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-25 - In-Console Feed Control (admin Feed tab, v3.5.0)
**Date:** 2026-07-06
**Severity:** FULL
**Decision:** Add an admin-only **Feed** tab to the console that configures the USAspending query the feeder (Component F) runs: award types (friendly categories mapped to USAspending `award_type_codes`), a look-back window, and a per-pull size. **Save** (PUT /feed/config) persists a small JSON config to `reference/feeder-config/current.json` (which the SCHEDULED feeder reads each run); **Run now** (POST /feed/run) invokes the feeder `live` alias immediately with the posted filters inline. The feeder gains `_load_config(event)` with precedence: inline event `feeder_config` (Run-now) > the saved S3 config (schedule) > env defaults (v3.3.0 behavior unchanged). Admin-only is enforced BOTH at the edge (a resource-policy Deny on `*/*/feed/*` for reviewer/auditor/submitter, overriding the auditor GET-allow) AND in the handler (`_is_admin`), mirroring the reference-publish control. The console API's execution role gains `lambda:InvokeFunction` on the feeder alias (the `reference/*` R/W it already had covers the config object); the feeder gains `s3:GetObject` on `reference/feeder-config/*`.
**Alternatives considered:**
- Keep filters in Terraform only (rejected: the request is to pick the data from inside the app, not by editing tfvars and re-applying).
- A full USAspending-builder clone (award types + AGENCY + LOCATION + date type) (deferred: agency/location need a picker and heavier API filters; the MVP is award types + window + size + Run-now, a clean fast-follow for agency/location).
- Store the config in the batch bucket or a new bucket (rejected: the reference bucket already has console-API R/W IAM under `reference/*`, so `reference/feeder-config/` is zero new IAM for the console; the feeder adds one narrow GetObject).
- Have Run-now read the saved S3 config (rejected in favor of passing the form's filters inline, so a run uses exactly what is on screen without forcing a Save first; Save still persists for the schedule).
**Rationale:** gives the admin a USAspending-style builder in-app that drives the real API pull on demand and on the schedule, reusing the feeder, the versioned-config idea, and the existing admin-gating pattern. Backward compatible: the schedule with no saved config still runs the v3.3.0 defaults.
**Risk acknowledged:** (1) Run-now writes real payments and permanent audit records immediately; bounded by the size cap (1-100, validated server-side) and the dev 1-day retention. (2) The config is user input; validated server-side (valid award codes only, window 1-3650, size 1-100) before it reaches the feeder. (3) The console API now invokes a Lambda (a new capability for that role); scoped to the one feeder alias ARN. (4) Agency/location filtering is deferred, so the in-app builder is narrower than usaspending.gov's; documented.
**Confidence:** HIGH. **Reversibility:** HIGH - the tab and routes are additive; removing them is a handler + UI revert, and the feeder falls back to defaults if the config object is absent.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-26 - Full Feed Builder: agencies, locations, sub-awards (v3.6.0, extends DEC-25)
**Date:** 2026-07-07
**Severity:** FULL
**Decision:** Extend the admin Feed builder (DEC-25) to the full USAspending search surface: award types now include Contract IDVs (IDV_A..E), Insurance (09), Other (11), and a Prime/Sub-Awards mode toggle (Sub-Contracts / Sub-Grants); awarding-or-funding **agency + sub-agency**; **location** (recipient or place-of-performance, country + state); **date type** (action / last-modified) and an explicit **from/to date range**. The feeder's `_fetch_awards` builds the full `spending_by_award` `filters` object plus the `subawards` flag (verified live 2026-07-07: sub-awards are the same endpoint with `{"subawards": true}` and `Sub-Award ID`/`Sub-Awardee Name`/`Sub-Award Amount` fields); `_to_payment` maps prime vs sub field names (sub ids prefixed `USASPEND-SUB-`). The console fetches the agency and sub-agency lists DIRECTLY from USAspending in the browser (verified `access-control-allow-origin: *`), so no backend proxy; states are a static list. Console API `_validate_feed` validates the richer config (known award codes incl. IDVs, agency `{type,tier,name}` shapes, location `{country,state?}`, date_type enum, ISO dates, size 1-100).
**Alternatives considered:**
- Proxy the agency/location lists through the console API (rejected: USAspending is CORS-open and keyless, so the browser fetches directly, no new backend/IAM).
- Let one query mix prime and sub-awards (rejected: the API's `subawards` flag is global per request; a Prime/Sub mode toggle is the honest model, matching how usaspending.gov produces separate files).
- Free-text agency entry (rejected: a dropdown from the live toptier list + dependent sub-agency dropdown is less error-prone and matches the builder).
**Rationale:** gives the admin the full usaspending.gov Custom Award Data search surface inside the console, reusing the DEC-25 config store, endpoints, IAM, and admin-gating unchanged (no new Terraform/IAM). Backward compatible: absent fields fall back to the v3.3.0 scheduled defaults.
**Risk acknowledged:** (1) A narrow filter set (e.g. a small agency + state + short window) can return zero rows; the feeder writes nothing and reports it, no crash. (2) `date_type` on the time_period is included in the request; if a future API change rejects it the feeder degrades to fetch_error (logged), never a bad screening. (3) More filter surface means more user input; all validated server-side before reaching the feeder. (4) Sub-award amounts/names are a different data shape; mapped explicitly and dropped if malformed.
**Confidence:** HIGH. **Reversibility:** HIGH - additive form controls + config fields; the feeder ignores unknown/absent fields and falls back to defaults.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-27 - Console restructure: three surfaces, Admin menu, Submit modal (v3.7.0)
**Date:** 2026-07-07
**Severity:** FULL
**Decision:** Collapse the console's six flat tabs into three primary surfaces and fold the occasional actions out of the top bar. (1) **Dashboard** (new `screens/Dashboard.jsx`): a flagged-item hero ("N payment(s) awaiting human review" with a jump to the queue, shown only when the queue is non-empty) on top of the existing executive Overview (`Showcase.jsx`), replacing the old Overview tab. (2) **Review Queue**: unchanged. (3) **Audit log**: the former Analytics screen (`canAnalytics`), retitled "Audit log & compliance", with the three headline counter cards removed (they now live on the Dashboard) and the immutable audit log + CSV export kept for auditors. Reference Data, Feed, and Demo controls move under a single admin-only **"Admin" dropdown** (`components/AdminMenu.jsx`); Submit Payment becomes a **"+ Submit payment" header button** opening the four-field form in a modal (`components/SubmitModal.jsx`), since the feeder is the real intake now. Landing is role-aware: `canReview` roles land on `#/dashboard`, others on `#/profile`; existing route guards bounce any role off a surface it cannot see.
**Alternatives considered:**
- Keep Submit as a full tab (rejected: it is now an occasional manual action, not the primary intake; a header button + modal declutters the nav and matches the streamlining request).
- Merge the audit log into the Dashboard too (rejected: the Dashboard is the at-a-glance exec view; the full audit table + CSV export is an auditor workflow that deserves its own surface, and keeping it `canAnalytics`-gated preserves the existing role boundary).
- A hamburger/sidebar nav (rejected: three top tabs + one Admin dropdown + the profile menu is simpler and preserves the existing tab styling; no new layout system).
**Rationale:** the exec sees the system (flagged item + live numbers) the moment they land, the review workflow is one click away, and admin config is grouped without cluttering the primary nav. Frontend-only: no Lambda, IAM, API, or Terraform change, so the gate is low-risk and deploys via the console SPA pipeline alone.
**Risk acknowledged:** (1) Menu items carry `role="menuitem"` (explicit role overrides the implicit button role); the test suite targets them by that role. (2) Moving Reference Data/Feed under a dropdown adds one click for admins; acceptable for a cleaner top bar. (3) No backend change means the role gating and edge Deny policies from DEC-25/DEC-26 are unchanged and still authoritative; the UI reshuffle cannot widen access.
**Confidence:** HIGH. **Reversibility:** HIGH - pure frontend refactor; reverting the console bundle restores the six-tab layout, and no data, IAM, or infra was touched.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-28 - Console UI refinement: up-to-5-tab nav, consolidated Admin, guided Tour (v3.8.0)
**Date:** 2026-07-07
**Severity:** FULL
**Decision:** Apply an external design handoff plus a user-directed IA change. (1) Primary nav becomes a clean left-to-right set of up to five role-gated tabs: `Dashboard | Review Queue | Audit log | Admin | Tour`. The v3.7.0 "Admin" nav dropdown (DEC-27) is retired and Reference data + Feed builder are consolidated into ONE `Admin` tab with sub-sections (`screens/Admin.jsx`), removing two loose pages; old `#/reference` / `#/feed` links resolve to the right Admin sub-tab for back-compat. (2) `Dashboard` is rebuilt as an executive operations view (live indicator, flagged-item hero, four plain-English KPI cards, outcome donut, flagged gauge, match-type bars) reusing the hand-built SVG charts, now exported from `Showcase.jsx`. (3) A new plain-English guided **Tour** (`screens/Tour.jsx`) walks a first-time user through eight top features in a semi-casual, semi-professional voice, with role-gated deep links. (4) Brand refresh (PG mark + "PrePayGuard" + subtitle). No backend, API, or screening-behavior change.
**Alternatives considered:**
- The handoff's exact IA (3 tabs, Admin + How-it-works moved into the account menu) (rejected on the user's direction: they wanted a 4-5 tab left-to-right flow, and burying admin config two levels deep in the avatar menu hurts discoverability for admins who use Reference data / Feed often).
- Keep Reference data and Feed as separate top tabs (rejected: that pushes an admin to six tabs; consolidating into one Admin tab with sub-sections hits the target 4-5 and groups the two "data that drives screening" surfaces).
- A spotlight-overlay product tour that highlights live DOM elements (rejected: fragile element targeting and positioning; a self-contained stepper page with deep links is robust, testable, and matches "showcase the top features").
- Keep the long narrative Showcase as its own tab (rejected: the Tour supersedes it as the explain-the-system surface; Showcase.jsx is retained only as the source of the reusable chart components).
**Rationale:** matches the design the user liked, hits their requested 4-5 tab flow, and adds an onboarding surface a stranger can learn the tool from, while reusing existing components/CSS and changing no screening behavior. The adjudication-note-into-decision "fix" the handoff calls substantive was already shipped (AuditDetail binds and submits the note), so it is a no-op here.
**Risk acknowledged:** (1) Sub-tab chips and nav buttons must stay plain buttons (no `role="tab"`/`menuitem`), or `getByRole("button")` in the suite breaks, same gotcha as DEC-27's menu items. (2) Retiring the standalone Showcase route drops the long narrative (points-system, three-decisions, built-for-trust essay) from the UI; the Tour covers the highlights, and the content can be re-surfaced if wanted. (3) Frontend-only, so role gating and edge Deny policies are unchanged and the reshuffle cannot widen access.
**Confidence:** HIGH. **Reversibility:** HIGH - pure frontend refactor; reverting the console bundle restores the prior IA, and no data, IAM, or infra was touched.
**Resolution:** PROCEED
**Status:** LOCKED

---

## DEC-29 - Payee input validation at Component A intake, rail-sized, fail-closed (Phase 2.1e, v3.9.0)
**Date:** 2026-07-09
**Severity:** FULL
**Decision:** Enforce payee validation at intake, flag-gated (`payee_validation_enabled`, default **ON**), at two layers that toggle together: (1) the API Gateway request model gains `maxLength = 35` and `pattern = "^[ -~]+$"` (printable ASCII 0x20-0x7E) on `payee`; (2) Component A's handler (`_validate_payee`, `src/component_a_intake/app.py`) re-validates length + printable-ASCII and returns **400** on violation, **before** the idempotency write and SQS enqueue, so an invalid payee is never screened and never approved (fail-closed). `PAYEE_MAX_LENGTH` env (default 35) is honored by the handler. Setting the flag off restores the exact pre-2.1e unbounded schema (`{string, minLength 1}`) and handler behavior so the demo can reproduce the F1 matcher-evasion attack live. This is the primary remediation for the F1 / 2.1a root cause (Component A accepted unbounded free text); it does NOT implement windowed matching (that stays recommended follow-on).
**Alternatives considered:**
- **Cap at NACHA 22 instead of Fedwire 35** (rejected as default): 2.1d measured the cap's own cost against the live 96-entry v4 list — a 22-char cap makes 8/96 listed entities a full screening MISS if it truncates, or bounces 29/96 legitimate long names if it rejects; 35 reduces that to 2/96 or 11/96 while still bounding the field. 22 remains reachable via `PAYEE_MAX_LENGTH` for a stricter policy.
- **Truncate `payee` to the cap instead of rejecting** (rejected): 2.1b showed trailing truncation is defeated by prefix/infix placement, and 2.1d(b) showed a truncating cap introduces its own false-negative (a truncated legit long name misses its own listed entity). Rejecting (fail-closed) is safe; the availability cost of bounced long names is operator-handled.
- **Single-script-consistency character rule** (rejected as insufficient): 2.1d(a) proved a full Cyrillic transliteration is single-script yet evades the matcher (cosine 0.11-0.29), so a single-script rule does not close the class.
- **Latin-script-only + NFKC (allow diacritics)** (deferred, documented): lower false-reject (accepts `José Muñoz`) and folds fullwidth, but needs NFKC normalization + Unicode script checks — more complex and not expressible in the API Gateway `pattern`. Recorded in the threat model as the follow-on refinement.
**Rationale:** repairs the input contract (the 2.1a/2.1c root cause) at the edge and in-handler, cheaply, without touching the matcher (no eval re-sweep needed). Sized to a real federal rail (Fedwire 35). Flag-gated default-ON preserves the demo's ability to show the attack.
**Risk acknowledged:** (1) **KNOWN LIMITATION — this does NOT close F1.** 2.1d measured the residual: **75/96 (78%) listed entities remain evadable** via an in-budget ASCII append under a 35-char cap; the windowed matcher is the recommended backstop, not built here. (2) ASCII-printable **rejects legitimate diacritic names** (`José Muñoz`, `François`) — a real false-reject, asserted in `test_ascii_rule_rejects_legitimate_diacritics_known_limitation`; the Latin-script+NFKC variant is the documented mitigation. (3) Rejecting `payee` over 35 chars bounces the 11/96-equivalent legitimately long names (availability), to be routed out-of-band. (4) The edge `pattern` relies on API Gateway request-body validation; the in-handler check is the defense-in-depth / direct-invoke guarantee.
**Confidence:** HIGH (matcher unchanged; measured tradeoffs). **Reversibility:** HIGH — single Terraform flag returns the prior schema and handler behavior; no data/IAM/infra migration.
**Resolution:** PROCEED
**Status:** LOCKED

---

# 29 decisions logged. 29 LOCKED, 0 OPEN.
