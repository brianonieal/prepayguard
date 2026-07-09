# CLAIMS register (V2) — every handoff numeric claim, traced to its artifact

**Date:** 2026-07-09. One row per numeric claim destined for the handoff package. "Data file"
= the committed artifact holding the value. "Gen. script" = the artifact that regenerates it.
"Repro?" = can a successor reproduce the number **from the committed repo alone** (Y), or is
something missing (N / partial).

## ⚠ Headline gap (read first)

**Update (V8, 2026-07-09): the four matcher-evasion sweep scripts are now COMMITTED** to
`scripts/` (`sweep_2_1b.py`, `sweep_2_1d.py`, `sweep_2_1d2.py`, `sweep_c4.py`) with a shared
`scripts/evasion_common.py`. They build reference vectors by **re-embedding the names from the
committed V3 snapshot** (Titan is deterministic — 0.00 drift — so `embed(name)` reproduces the
stored vector exactly, verified: cos 1.000000). Each was **re-run and reproduced its committed
JSON numbers** (75/96, 31/96, 29/11, max 66, full-Cyrillic evades-all, homoglyph Hawwk k2 0.5194,
C4 unmatchable 1/11). So 2.1b / 2.1d / C4 flip **N → Y**.

**Still NOT reproducible:** the **2.0b/2.0c generator** was authored in a prior session and is not
in this scratchpad; rows 7–8 remain **N** (committed data only). Reconstructing it would be a
re-derivation, not done. The **C1/C2 recall splits** (rows 11–12) are recomputable from committed
data but have no committed split script (**partial**).

## Register

| # | Claim | Value | Data file (committed) | Gen. script | Repro? |
|---|---|---|---|---|---|
| 1 | Residual evadable under 35-char cap | **75/96 (78.1%)** | `matcher_evasion_bounded_data.json` → `2_1d_residual_N_of_96.cap_35` | **`scripts/sweep_2_1d2.py`** (committed, V8) | **Y** (reran → 75) |
| 2 | Residual evadable under 22-char cap | **31/96 (32.3%)** | `matcher_evasion_bounded_data.json` → `…cap_22` | **`scripts/sweep_2_1d2.py`** (committed, V8) | **Y** (reran → 31) |
| 3 | Reference-name length: min / max / mean | **6 / 66 / 21.5** | `matcher_evasion_bounded_data.json` → `2_1d.b_length_hist` | **`scripts/sweep_2_1d.py`** (committed, V8); also derivable from the V3 snapshot | **Y** |
| 4 | Names exceeding 22 / 35 chars | **29 / 11** (of 96) | `…b_length_hist` | **`scripts/sweep_2_1d.py`** (committed, V8) | **Y** (reran → 29 / 11) |
| 5 | Full-Cyrillic transliteration cosines | **0.11–0.29** (all 5 evade) | `matcher_evasion_bounded_data.json` → `2_1d.a_full_script` | **`scripts/sweep_2_1d.py`** (committed, V8) | **Y** |
| 6 | 2.1b bounded-append evasion | 3/5 @35, 2/5 @22; homoglyph `Наwwk`→0.519 | `matcher_evasion_bounded_data.json` → `entities`, `homoglyph_nsub_sweep` | **`scripts/sweep_2_1b.py`** (committed, V8) | **Y** (reran → k2 0.5194) |
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
| 17 | C4: long entities unmatchable under cap | **exactly 1 of 11** (`SCIENTIFIC…MEASURING TECHNOLOGY`); 8/11 semantic-only on realistic forms | `matcher_evasion_bounded_data.json` → `C4_long_entity_cap_matchability` | **`scripts/sweep_c4.py`** (committed, V8) | **Y** (reran → 1/11) |
| 20 | Semantic sweep production FPs @0.72 (C5) | **7 of 16 hard negatives ≥0.72** (2 at 0.966) | `semantic_eval_results_v2.json` (per_case) | **`scripts/eval_semantic_matching.py`** (committed) | **Y** |
| 21 | ECR image-scan findings (deployed tag v3.8.3) | **2 HIGH + 1 MED + 1 LOW per image** (sqlite/libxml2/gnupg2, amzn2023 base) | `docs/evidence/scans/ecr-image-scan-2026-07-09.txt` | `aws ecr describe-image-scan-findings` (ECR scan-on-push) | **Y** (needs ECR access) |
| 18 | Deployed-API validation test (2.1f) | 66-char→400, Cyrillic→400, clean→200 | none (results in `matcher_evasion_bounded.md` §e prose) | **`scripts/send_payment.py`** (committed) against live dev API | **Y** (needs live infra) |
| 19 | Reference list size / version | **96 entries, v4** | V3 snapshot `docs/evidence/reference_list_v4_snapshot.*` | live S3 `reference/current.json` | **Y** once V3 lands |

## Summary (after V8)

- **Fully reproducible from the repo (Y): 19 of 21 rows** — the four matcher-evasion sweeps
  (2.1b, 2.1d, residual, C4, now committed + reran), the semantic-eval sweep (both sets), the C5
  production-FP count, the three Bedrock-cost figures, stability, the deployed test, the
  reference size, and the ECR image-scan findings.
- **NOT reproducible (N): 2 rows** — the **2.0b/2.0c** dilution figures (rows 7–8): their
  generator was authored in a prior session and is not available; committed data only.
- **Partial (2 rows):** the **C1/C2** recall splits (rows 11–12) — committed data, recomputable,
  but no committed split script.

Remaining gaps for the handoff: reconstruct or locate the 2.0b/2.0c generator (rows 7–8), and
optionally save the C1/C2 split as a committed script (rows 11–12).
