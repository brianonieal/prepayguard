# SPEC.md
# Current-gate detail. Updated each gate.

## LAST CLOSED: v0.3.0 — Components B & C (Enrichment + Risk Scoring)
**Status:** WORK COMPLETE, ALL CRITERIA MET — awaiting GO certification.
CONFIRMED ✓ · ROADMAP APPROVED ✓ · DEC-14 logged ✓ · pytest 14/14 ·
fmt/validate/tflint clean · checkov 271/0 · plan 77/0/0 (no `.tf` change).

- **B (enrichment):** matches payee against bundled synthetic DNP reference list
  (TIN + exact/fuzzy name), attaches `enrichment` block → Component C.
- **C (risk scoring):** rule-based score → three-way disposition (TIN→reject,
  name→review, none→approve), attaches `risk` block → Component D.
- Message schema now: `payment → +enrichment → +risk`. Handlers:
  `src/component_b_enrichment/app.py`, `src/component_c_risk_scoring/app.py`.

## NEXT GATE: v0.4.0 — Component D (Disposition, Audit, Notify)
Consumes the scored message: writes immutable audit record to S3 Object Lock
(**commitment 4**), routes `review` dispositions to the human-review queue
(**commitment 2**), posts a webhook via least-priv Secrets Manager (DEC-7).
Three evidence tests (object lock, failure routing, review notification).
Opens on **GO**.

## DECISIONS SNAPSHOT
14 of 14 LOCKED. No open questions.
