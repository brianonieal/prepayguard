# AI_ASSISTED_DEVELOPMENT.md

Course objective 2: AI-assisted development used with judgment. This documents where
AI assistance was used to build PrePayGuard, how it was reviewed, and how it was
tested, with concrete examples of judgment applied (including where AI-proposed
approaches were rejected or corrected). No em dashes are used in this project's docs
by standing convention.

## 1. Tooling and method

PrePayGuard was built with AI-assisted development under a gated, human-approved
workflow (the "Blueprint" method), not free-form generation:

- **Assistant:** Claude Code (Opus) for planning, code, tests, Terraform, and docs.
- **Approval gates:** every version passed explicit human checkpoints (CONFIRMED,
  ROADMAP APPROVED, and a GO gate per version) before work was accepted. The operator
  approved scope before code and reviewed the result before each gate closed.
- **Decision pressure-testing:** load-bearing decisions were run through an adversarial
  critique step before being accepted, and each was recorded in
  `foundation/DECISIONS.md` with its alternatives considered, the objections raised,
  and their resolution. That file is the audit trail of AI-assisted-but-human-owned
  decision making (22 locked decisions).
- **Structured debugging:** persistent failures were diagnosed with a root-cause step
  rather than trial-and-error patching.

## 2. Where AI assistance was used

- **Handler code:** Components A to E and the console API (Python).
- **Infrastructure:** the Terraform modules (shared `queue_worker_stage`,
  `api_intake_stage`, `audit_store`, `reference_store`, `console_*`, etc.).
- **Tests:** the commitment and behavior tests, written to guard the generated logic.
- **Console:** the React/Vite reviewer SPA.
- **This SME hardening pass:** the semantic evaluation, the Bedrock cost measurement,
  the real-source ingestion, and the docs under `docs/sme/`.

## 3. How it was reviewed

- **Human approval at every gate**, as above. Nothing merged on the assistant's say-so.
- **Decisions carry their reasoning**, so a reviewer can see why each path was chosen
  and what was rejected (`DECISIONS.md`), rather than trusting generated output blindly.
- **Static analysis on every change:** ruff, checkov, tflint, and pip-audit in CI
  (DEC-8, DEC-9), so generated code met the same bar as hand-written code.
- **Verify-before-acting in this pass:** every SME work order was checked against live
  repo state before any change, and every external claim (live deployment, Bedrock
  access, pricing, SAM access terms) was confirmed with a live check and dated, not
  taken from memory.

## 4. How it was tested

Generated logic is pinned by tests so that a regression or a subtle generation bug
fails loudly:

- **Adversarial commitment tests:** the idempotency store has a concurrent-duplicate
  race test and a crash-between-writes test (DEC-13), written before the gate closed.
- **Control-flow tests for the semantic layer:** that it runs only when string rules
  miss, degrades on a Bedrock error rather than dropping the payment, and is skipped
  when a string rule already matched (`tests/test_enrichment.py`).
- **Deterministic metric tests:** the semantic-eval precision/recall/FPR math is pinned
  without any Bedrock call (`tests/test_semantic_eval.py`).
- **Real-data normalization tests:** the SAM ingestion normalizer, dedupe, severity
  mapping, and rate-limit handling are pinned with no network or Bedrock
  (`tests/test_sam_ingest.py`).
- Totals: 109 pytest and 31 vitest, green in CI, plus per-gate live end-to-end runs.

## 5. Judgment applied (where AI proposals were rejected or corrected)

AI assistance was used with judgment, not accepted uncritically. Concrete examples:

- **DEC-13:** the AWS Lambda Powertools idempotency decorator was correct-by-
  construction but hides the mechanism; it was rejected in favor of visible hand-rolled
  PENDING to SENT logic because the deliverable is demonstrating idempotency, and the
  hand-roll's risk was converted to evidence with adversarial tests.
- **DEC-14:** a machine-learning risk model was rejected in favor of transparent
  rule-based scoring, because an opaque model is not gradeable as "show the mechanism"
  and the real Do Not Pay pattern is match/rule-based.
- **DEC-19:** a managed vector database (~$700/mo) was rejected in favor of in-store
  cosine (~$2/mo idle) for a list of hundreds of entries.
- **SME pass, ground rules honored:** capabilities were never mocked and presented as
  working. When the real public data tier could not support the full list, it was
  scoped down and labeled (DEC-22 size cap), not faked.
- **SME pass, live findings corrected generated assumptions:** the SAM API contract was
  corrected from live behavior (an `Accept: application/json` header returns 406; the
  records are nested, not flat), the free key's 10/day rate limit was discovered by a
  real 429 and the fetch redesigned around it, and a normalization bug (the substring
  "active" matches "Inactive") was caught by a test and fixed. Each correction came from
  verification, not assumption.

## 6. Honest limitation

AI assistance accelerated production of code, tests, and docs, but the correctness
guarantees come from the human approval gates, the recorded decision rationale, the
test suite, and the static analysis, not from the assistant. The residual risk of a
subtle generation bug is mitigated, not eliminated; the adversarial tests and the
verify-before-acting discipline are the controls that keep it bounded.
