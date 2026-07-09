# CLAIMS register (V2) — every handoff numeric claim, traced to its artifact

**Date:** 2026-07-09. One row per numeric claim destined for the handoff package. "Data file"
= the committed artifact holding the value. "Gen. script" = the artifact that regenerates it.
"Repro?" = can a successor reproduce the number **from the committed repo alone** (Y), or is
something missing (N / partial).

## ⚠ Headline gap (read first)

**The matcher-evasion sweep scripts are NOT committed.** `sweep_2_1b.py`, `sweep_2_1d.py`,
`sweep_2_1d2.py`, `sweep_c4.py`, and the 2.0b/2.0c generator live only in the session scratchpad
(`…/scratchpad/`), not in the repo. Their **output JSON is committed** (`matcher_evasion_*.json`),
so every value is backed by a committed *data* artifact — but **cannot be re-derived from the
repo** because the generating code is absent. That covers roughly half the headline numbers
(all of 2.1b / 2.1d / C4 / 2.0b / 2.0c). Only the **semantic-eval** and **Bedrock-cost** numbers
have both a committed script and committed data (fully reproducible). This is a real handoff gap;
it is flagged here, not backfilled. **Recommendation: commit the four sweep scripts to
`scripts/` (or `docs/evidence/`) to flip the N rows to Y.** Not done in this pass (out of the
C1–C4 edit scope).

## Register

| # | Claim | Value | Data file (committed) | Gen. script | Repro? |
|---|---|---|---|---|---|
| 1 | Residual evadable under 35-char cap | **75/96 (78.1%)** | `matcher_evasion_bounded_data.json` → `2_1d_residual_N_of_96.cap_35` | `scratchpad/sweep_2_1d2.py` **(not committed)** | **N** (data only) |
| 2 | Residual evadable under 22-char cap | **31/96 (32.3%)** | `matcher_evasion_bounded_data.json` → `…cap_22` | `scratchpad/sweep_2_1d2.py` **(not committed)** | **N** (data only) |
| 3 | Reference-name length: min / max / mean | **6 / 66 / 21.5** | `matcher_evasion_bounded_data.json` → `2_1d.b_length_hist` | `scratchpad/sweep_2_1d.py` **(not committed)**; also derivable from the V3 reference snapshot | **N** (script); data + snapshot committed |
| 4 | Names exceeding 22 / 35 chars | **29 / 11** (of 96) | `…b_length_hist` | `scratchpad/sweep_2_1d.py` **(not committed)** | **N** (data only) |
| 5 | Full-Cyrillic transliteration cosines | **0.11–0.29** (all 5 evade) | `matcher_evasion_bounded_data.json` → `2_1d.a_full_script` | `scratchpad/sweep_2_1d.py` **(not committed)** | **N** (data only) |
| 6 | 2.1b bounded-append evasion | 3/5 @35, 2/5 @22; homoglyph `Наwwk`→0.519 | `matcher_evasion_bounded_data.json` → `entities`, `homoglyph_nsub_sweep` | `scratchpad/sweep_2_1b.py` **(not committed)** | **N** (data only) |
| 7 | 2.0c 5-token dilution (adversarial) | fuzzy **0.487**, semantic **0.506** at 5 tok | `matcher_evasion_data.json`, `matcher_evasion_distance_data.json` | 2.0b/2.0c generator **(not committed)** | **N** (data only) |
| 8 | 2.0c distance-vs-length (5 real SAM entities) | 4/5 classes evade at 5 tok | `matcher_evasion_distance_data.json` → `d_real_entities_length5` | 2.0c generator **(not committed)** | **N** (data only) |
| 9 | Semantic sweep, 27-case set @0.72 | prec 0.833, recall 1.000, F1 0.909, FPR 0.118 | `semantic_eval_results.json` | **`scripts/eval_semantic_matching.py`** (committed) + `scripts/semantic_eval_set.json` (pre-2.4 state in git history) | **Y** |
| 10 | Semantic sweep, 62-case set @0.72 | prec 0.682, recall(all) 0.484, F1 0.566 | `semantic_eval_results_v2.json` | **`scripts/eval_semantic_matching.py`** (committed) + `scripts/semantic_eval_set.json` (committed, 62 cases) | **Y** |
| 11 | Recall split (C1) benign / append @0.72 | **10/10 = 1.00** / **5/21 = 0.24** | `semantic_eval_results_v2.json` (per_case) | derived (ad-hoc scratchpad analysis, **not committed**); recomputable from committed data + `semantic_eval_set.json` variants | **partial** (data committed; no committed split script) |
| 12 | Matcher recall on validated input (C2) | **10/16 = 0.625** (benign 9/9, append 1/7) | `semantic_eval_results_v2.json` (per_case) + 35-char filter | derived (scratchpad, **not committed**); recomputable | **partial** |
| 13 | Embedding stability (drift) | **0.00e+00** | printed by `--stability` (not persisted to a file) | **`scripts/eval_semantic_matching.py --stability`** (committed) | **Y** (recompute; value not stored) |
| 14 | Bedrock cost per embed | **~$0.0000001** (~5 tok, ~$0.10/M) | `docs/BEDROCK_COST.md` | **`scripts/measure_bedrock_cost.py`** (committed) | **Y** |
| 15 | Bedrock cost per 1000 payments | **~$0.0001 / 1000** (worst case) | `docs/BEDROCK_COST.md` | **`scripts/measure_bedrock_cost.py`** (committed) | **Y** |
| 16 | Brief cost | **~$0.000035 / brief** | `docs/BEDROCK_COST.md` | **`scripts/measure_bedrock_cost.py`** (committed) | **Y** |
| 17 | C4: long entities unmatchable under cap | **≥1 of 11** (`SCIENTIFIC…MEASURING TECHNOLOGY`) | `matcher_evasion_bounded_data.json` → `C4_long_entity_cap_matchability` | `scratchpad/sweep_c4.py` **(not committed)** | **N** (data only) |
| 18 | Deployed-API validation test (2.1f) | 66-char→400, Cyrillic→400, clean→200 | none (results in `matcher_evasion_bounded.md` §e prose) | **`scripts/send_payment.py`** (committed) against live dev API | **Y** (needs live infra) |
| 19 | Reference list size / version | **96 entries, v4** | V3 snapshot `docs/evidence/reference_list_v4_snapshot.*` | live S3 `reference/current.json` | **Y** once V3 lands |

## Summary

- **Fully reproducible from the repo (Y): 8 rows** — the semantic-eval sweep (both sets), the
  three Bedrock-cost figures, stability, the deployed test, and the reference-size (post-V3).
- **Data committed but NOT reproducible (N): 9 rows** — every matcher-evasion number (2.1b,
  2.1d, 2.1d residual, full-Cyrillic, C4) and the 2.0b/2.0c dilution figures, because their
  sweep scripts are scratchpad-only.
- **Partial (2 rows):** the C1/C2 recall splits — committed data, but the split was computed by
  an ad-hoc analysis not saved as a script.

The N and partial rows are the ones a reviewer cannot independently rerun today. Closing them
is a one-commit action (add the four sweep scripts) and is recommended before the handoff ships.
