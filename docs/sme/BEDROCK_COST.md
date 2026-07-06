# BEDROCK_COST.md — measured Bedrock cost of the two LLM paths

Course objective 5 (cost sub-requirement + responsible-use sub-point). The repo
had cost REASONING (DEC-19: ~$2/mo idle baseline vs ~$700/mo for a managed vector
DB; DEC-20: "~$0.0001/brief") but no MEASURED per-invocation cost from a real run.
This closes that with real token counts times current published pricing.

- Measured: 2026-07-06, account <ACCOUNT_ID>, us-east-2.
- Reproduce: `python scripts/measure_bedrock_cost.py` (real Bedrock; token counts
  from live responses). Embedding counts also come from the WO1 eval run.

## 1. Pricing (live-checked, pinned with date)

Confirmed via the **AWS Price List API** (`ServiceCode=AmazonBedrock`), us-east-2
(Ohio), on **2026-07-06**. Not remembered prices; queried from AWS:

| Model (id) | usagetype | Rate |
|---|---|---|
| Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`) | `USE2-TitanEmbeddingV2-Text-input-tokens` | **$0.00002 / 1K input tokens** (no output charge) |
| Nova Lite (`amazon.nova-lite-v1:0`) | `USE2-NovaLite-input-tokens` | **$0.00006 / 1K input tokens** |
| Nova Lite (`amazon.nova-lite-v1:0`) | `USE2-NovaLite-output-tokens` | **$0.00024 / 1K output tokens** |

These are the exact model ids the repo deploys (`environments/dev/main.tf`).
Re-confirm if AWS changes pricing: `aws pricing get-products --service-code
AmazonBedrock --region us-east-1 --filters Type=TERM_MATCH,Field=usagetype,Value=USE2-NovaLite-input-tokens`.

## 2. Measured token counts and cost (real run, 2026-07-06)

Semantic embedding path (Component B `_semantic_match` -> Titan): embedding the
full WO1 labeled set (8 reference names + 27 test payees):

- **35 embedding calls, 175 input tokens total** (avg 5.0 tokens per payee name).
- Cost = 175 / 1000 x $0.00002 = **$0.0000035** for the whole set.
- **Per semantic evaluation: ~$0.0000001** (about $0.10 per one million payee
  embeddings). Effectively free at any demo or course-scale volume.

Adjudication brief path (console API `_llm_brief` -> Nova Lite, real BRIEF_SYSTEM
prompt over representative flagged records):

- **3 briefs: 724 input + 260 output tokens** (avg 241 in / 87 out per brief).
- Cost = 724/1000 x $0.00006 + 260/1000 x $0.00024 = $0.00004344 + $0.0000624 =
  **$0.0001058** for 3 briefs.
- **Per brief: ~$0.000035** (about $35 per one million briefs).

## 3. The concrete demo-run line

Measured demo run (the exact 2026-07-06 run):

> **35 semantic evaluations = $0.0000035; 3 adjudication briefs = $0.0001058;
> total demo-run Bedrock cost = $0.00011.**

A fuller live demo (screen ~50 payments, all reaching the semantic path, plus ~10
reviewer briefs) projects to about **$0.0004 total** at these measured rates. The
active inference cost is negligible; the cost story that matters is architectural,
and it already sits in DEC-19: cosine-in-store keeps the idle baseline at ~$2/mo
versus ~$700/mo for an always-on managed vector database. The measurement confirms
that per-invocation inference adds effectively nothing on top of that baseline.

Note vs the prior estimate: DEC-20 guessed "~$0.0001/brief"; the measured figure
is ~$0.000035/brief, roughly 3x cheaper. The estimate was conservative, which is
the safe direction, and the measurement now replaces it.

## 4. Stability of the cost (a real difference between the two paths)

- The **embedding** path is deterministic (SEMANTIC_EVAL.md: 0.00 vector drift),
  so its token count and cost are exactly reproducible.
- The **brief** path is NOT deterministic: Nova Lite output length varies slightly
  run to run (observed 260 to 273 output tokens across runs for the same 3
  records), so per-brief cost drifts by a fraction of a percent. It is bounded
  above by `maxTokens: 300` output per brief = at most 300/1000 x $0.00024 =
  $0.000072 of output plus input, so a brief can never exceed ~$0.0001 regardless.

## 5. Responsible use (verified, not asserted)

The reviewer brief is **advisory only and never enters the immutable record**.
Verified in code, `src/console_api/app.py:165-196`: `_llm_brief` reads fields from
the already-written audit record and calls Bedrock `converse`; `_brief` returns
the text inline in the HTTP response. Neither writes to S3, the audit record, the
audit index, or the reviews table, and neither influences scoring. The endpoint is
GET-only and read-only. This matches DEC-20 and the immutability boundary holds:
the human reviewer makes and owns the decision; the brief only accelerates reading
the evidence that is already in the record.
