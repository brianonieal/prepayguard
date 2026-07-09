# ORIENTATION.md: PrePayGuard system analysis (SME pass)

Course objective 3 (analyze the system: architecture, dependencies, failure
modes, known unknowns). Written after reading the live repo at branch
`sme-hardening`, not a zip snapshot. Every claim below was checked against the
actual files cited; where a prior document is stale, this note says so.

Date of this pass: 2026-07-06. Repo state: `main` at commit `26a4046`
(v3.2.1), then branched to `sme-hardening`.

---

## 1. What the system is

A pre-payment integrity screening pipeline modeled on the U.S. Treasury Bureau
of the Fiscal Service Do Not Pay program. A payment is screened before it is
paid; it is approved, routed to a human reviewer, or rejected; every disposition
is written to an immutable audit record. A React console sits on top for human
adjudication, analytics, and reference-list administration.

It is a faithful reproduction of the Do Not Pay pattern. Its novelty is
near-floor by construction, and the honest edge is execution quality,
transparency (every disposition carries reason codes and a cited list version),
and one differentiating component: the semantic-matching layer in Component B.

---

## 2. Component inventory (verified against `src/` and `modules/`)

| Component | File | Role | Trigger | Key decisions |
|---|---|---|---|---|
| A. Payment Intake | `src/component_a_intake/app.py` | IAM-authed intake, payment-ID idempotency (PENDING to SENT), enqueue | API Gateway (AWS_IAM) | DEC-5, DEC-13 |
| B. Enrichment and Reference-Match | `src/component_b_enrichment/app.py` | Match payee/TIN against the Do Not Pay list: TIN exact, name exact, name fuzzy, name **semantic** | SQS | DEC-14, DEC-18, DEC-19 |
| C. Risk-Scoring and Decision | `src/component_c_risk_scoring/app.py` | Transparent rule-based score to a three-way disposition | SQS | DEC-14 |
| D. Disposition Router and Audit | `src/component_d_disposition/app.py` | Audit-first immutable write, route review items, webhook notify | SQS | DEC-4, DEC-7 |
| E. Batch Ingest | `src/component_e_batch_ingest/app.py` | S3-triggered bulk CSV/Excel/JSON intake, reuses A's queue and idempotency table | S3 event | DEC-16 |
| Console API | `src/console_api/app.py` | Reviews, audit fetch, decisions, batches, reference-data publish, LLM briefs, analytics | API Gateway (AWS_IAM) | DEC-15, DEC-17, DEC-18, DEC-19, DEC-20, DEC-21 |

Infrastructure is Terraform. Components B, C, D share one `queue_worker_stage`
module via `for_each` (DEC-1). Supporting modules: `api_intake_stage`,
`batch_ingest_stage`, `audit_store` (S3 Object Lock COMPLIANCE),
`review_queue`, `console_foundation` (Cognito, S3 and CloudFront, reviews
table), `console_api`, `reference_store` (versioned lists), `ecr_repo` (6x).

Model IDs are wired in `environments/dev/main.tf`: embeddings
`amazon.titan-embed-text-v2:0` (line 36), reviewer brief `amazon.nova-lite-v1:0`
(line 40). `SEMANTIC_THRESHOLD` default `0.72` (line 348).

---

## 3. Where the semantic layer lives (the differentiating component)

All in `src/component_b_enrichment/app.py`:

- `_embed(text)` (line 105): one Bedrock `invoke_model` call to Titan Embed Text
  v2, `normalize: true`, returns a 1024-dim unit vector.
- `_cosine(u, v)` (line 114): length-guarded cosine; returns 0.0 on any shape
  mismatch or empty vector.
- `_semantic_threshold()` (line 123): reads `semantic_threshold` from the
  versioned reference document if present, else the `SEMANTIC_THRESHOLD` env
  default (`0.72`). The threshold is versioned **with the list**.
- `_semantic_match(payment)` (line 130): embeds the payee, cosines against every
  reference entry that carries a stored `embedding`, returns the single best
  entry at or above threshold as a `name_semantic` match. On any Bedrock error
  it returns `[]` (degrade to rule-based screening, never DLQ).

Control flow (`match_against_reference`, line 157): the deterministic string
rules run first (TIN exact 95, name exact 80, fuzzy difflib >= 0.90 gives 60).
The semantic net runs **only when the string rules found nothing** (line 175),
so Bedrock is called only on the ambiguous residue. A semantic hit is capped to
REVIEW by Component C (`NAME_MATCH_CAP = 60`, `src/component_c_risk_scoring/app.py:27`),
never an auto-reject. Per-entry vectors are computed at publish time by the
console API and stored inside the versioned reference JSON, so there is no vector
database (DEC-19). This matches ARCHITECTURE.md and the README exactly.

Verified live from this machine (2026-07-06): a real Titan embed call returned a
1024-dim vector with `inputTextTokenCount`, and a real Nova Lite `converse` call
returned a `usage` block with input/output token counts. Both Bedrock paths are
reachable with the repo's model IDs, which is what makes a measured evaluation
(Work Orders 1 and 3) possible without fabricating numbers.

---

## 4. Tests (verified against `tests/`)

`pytest` baseline on this branch: **90 passed** (re-run 2026-07-06), `ruff`
clean. Test files:

- `test_idempotency.py` (commitment 1), `test_failure_routing.py` (commitment 2),
  `test_queue_depth_scaling.py` (commitment 3), `test_object_lock.py`
  (commitment 4), `test_review_notification.py` (DEC-7 webhook + scoped secret).
- `test_enrichment.py`: the string and semantic matching. Semantic cases mock
  `_embed` for determinism (`test_semantic_match_when_string_match_misses`,
  `_below_threshold_no_match`, `_skipped_when_string_matches`,
  `_bedrock_error_degrades_not_dlq`). These prove the **control flow** of the
  semantic layer; they do NOT measure its accuracy on real embeddings.
- `test_risk_scoring.py`, `test_console_api.py`, `test_component_e.py`.

Gap relevant to the SME work: there is no test or script that measures the
semantic layer's precision, recall, F1, or false-positive rate against real
Titan embeddings. The accuracy of the one differentiating component is currently
asserted (DEC-19 cites an informal "clean vendors ~0.24, true variants
0.86 to 0.97" observation), not measured. That is the Work Order 1 target.

---

## 5. Handoff package (current contents, and what is stale)

`docs/HANDOFF.md` is the **v1.0.0-era** package (dated 2026-07-03). It documents
Components A to D, 14 locked decisions, and 29/29 tests. It predates all of
Phase 3 and Phase 4: it does not mention the semantic layer, the LLM brief,
roles and segregation of duties, the versioned reference store, analytics, or
the console at their current state. The repo is now at 21 locked decisions and 90
tests. `docs/HANDOFF.docx` is the rendered twin of the same stale content.
**[Update 2026-07-09, v3.9.0: this paragraph is itself a historical snapshot. `docs/HANDOFF.md`
has since been brought current (Phase 2.1 security work, objective-5 eval, ERR-1, F5, ECR
findings) and `docs/HANDOFF.docx` was regenerated from it via pandoc — it is no longer stale.
The repo is now at 29 locked decisions and pytest `152 passed, 1 xfailed`.]**

Consequence for grading: there is currently no objective-5 section (evaluate LLM
workflows on performance, stability, cost, human review, responsible use) in the
handoff at all. Work Orders 1 and 3 create the evidence for it, and the handoff
needs a new objective-5 section pointing at that evidence.

Evidence files present and checked:
- `docs/evidence/live_object_lock_proof.txt`: real audit object, `delete_denied:
  true`, `shorten_denied: true`, both `AccessDenied`, verdict PASS. Supports the
  immutability claim and is the correct artifact to show instead of touching
  retention live (Work Order 4).
- `docs/evidence/live_e2e_run.txt`, `docs/evidence/console_live_e2e.txt`: prior
  live end-to-end proofs.

---

## 6. Live deployment (independent verification, 2026-07-06)

The README claims `https://d2rbxaf6pqgvb1.cloudfront.net` is up and access-
provisioned. Independently verified from this machine: `GET /` returns HTTP 200,
`Content-Type: text/html`, `<title>Treasury Console</title>`, and the React root
`<div id="root"></div>`; security headers present (HSTS, X-Frame-Options DENY,
nosniff). The SPA shell serves. This confirms the site is live and returns the
login screen; it does not by itself exercise the signed-in end-to-end flow (that
requires provisioned Cognito credentials), which the evidence files cover.

---

## 7. Dependencies and failure modes relevant to the SME work

- Bedrock is a soft dependency in B: an outage silently disables the semantic net
  (screening degrades to rules). This is a control that can quietly weaken; DEC-19
  flags it and notes the alarm is a follow-on.
- The reference list (and its per-entry vectors and threshold) is versioned in S3
  (DEC-18). A screening cites the exact `reference_version` it matched, so an
  evaluation must pin the list version to be reproducible.
- Titan embeddings are deterministic for a fixed model version, so a threshold
  sweep is reproducible; this is testable and is part of Work Order 1's stability
  note.

---

## 8. Known unknowns this pass surfaced

- Real precision/recall/FPR of the semantic layer at 0.72 and nearby thresholds
  (Work Order 1).
- Measured per-invocation Bedrock cost for the embed and brief paths from real
  token counts at current pricing (Work Order 3).
- Whether wiring one real reference source (SAM.gov exclusions) is feasible under
  current public access terms without breaking the synthetic-data discipline for
  the three restricted sources (Work Order 2, requires a live access-terms check
  at build time).
