# DECISIONS.md — PrePayGuard ("Treasury")
# Seeded at foundation build (v0.1.0, 2026-07-03) verbatim from TREASURY_DECISIONS_LOG.md.
# DEC-1..12 seeded verbatim; DEC-13+ added during build. Running total: 16 LOCKED, 0 OPEN.
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

# 16 decisions logged. 16 LOCKED, 0 OPEN.
