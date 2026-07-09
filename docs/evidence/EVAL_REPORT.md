# Semantic matcher evaluation report (Phase 2.3 — course objective 5)

**Date:** 2026-07-09. **Method:** live `amazon.titan-embed-text-v2:0` (us-east-2), the
deployed matcher's own `best_match` logic (`scripts/eval_semantic_matching.py`, which imports
Component B's cosine). This report covers two runs: the original **27-case** set (§2.3 —
10 positives / 10 clean / 7 hard negatives; results `semantic_eval_results.json`) and the
**append-inclusive 62-case** expansion (§2.4 — 31 / 15 / 16; results
`semantic_eval_results_v2.json`). `scripts/semantic_eval_set.json` **now holds the 62-case
version**; the 27-case state is in git history (pre-2.4). Where a section says "27-case", it
means the §2.3 run, not the current file. Reproduce:
`python scripts/eval_semantic_matching.py --stability --json docs/evidence/semantic_eval_results.json`.

## The strongest finding: the append-positive and hard-negative distributions overlap — no threshold separates them

> **There is no cosine threshold `t` at which every append-class positive scores ≥ `t` and every
> hard negative scores < `t`. The two distributions overlap, so a threshold that admits diluted
> listed names also admits genuinely different similar names. Re-tuning the threshold cannot fix
> this; it is a property of the embedding space, not of my case-mix.**

*(This corrects an earlier draft that claimed benign positives sit "cleanly above the hard
negatives" using min/max intervals. That was wrong — see below. The min/max framing distinguishes
nothing because the intervals nest; the correct statement is about distribution overlap.)*

Measured on the expanded set (§2.4, `semantic_eval_results_v2.json`):

- **The 21 append-class positives span 0.499–0.882.** The 16 hard negatives span 0.351–**0.966**.
- **Separation test (explicit): is there a `t` with all-append ≥ `t` AND all-hard-neg < `t`? NO.**
  It needs `min(append) > max(hard-neg)`, i.e. `0.499 > 0.966` — false. Concretely, **12 of the
  16 hard negatives sit at or above the lowest append positive (0.499)**, and **4 hard negatives
  (0.966, 0.966, 0.952, 0.876) sit at or above the entire benign-variation band (0.831–0.963)**.
  So no threshold cleanly separates append positives from hard negatives, and hard negatives are
  not even cleanly separated from *benign* positives.
- Full sorted hard-negative distribution: `0.966 Initech Solutions LLC`, `0.966 Globex Onshore
  Inc`, `0.952 Initech Systemics LLC`, `0.876 Globex Ashore Inc`, `0.815 Acme Shelling Co`,
  `0.798 Robert Rowe`, `0.743 Umbrella Insurance Group`, then 0.701, 0.650, 0.637, 0.570, 0.565,
  0.489, 0.437, 0.426, 0.351.

A threshold low enough to admit the diluted names (≈0.50) admits nearly every hard negative;
0.72 misses the diluted names *and still* misclassifies the top hard negatives (next finding).
The overlap is a fixed property of the geometry — Titan places a listed name diluted by distant
tokens in the same region as a *different* company sharing a token — so **input validation (bound
the string before it is embedded), not re-tuning, is the lever.**

## Separate finding (previously unreported): 7 production false positives at the deployed 0.72

Because the distributions overlap at the top, **7 of the 16 hard negatives score ≥ 0.72 and are
therefore false positives in production** at the deployed threshold — each flags a *different*
entity as a match, sending a clean payment to human review:

| hard-negative payee | cosine | matched (wrongly) to |
|---|---|---|
| `Initech Solutions LLC` | 0.966 | Initech Systems LLC |
| `Globex Onshore Inc` | 0.966 | Globex Offshore Inc |
| `Initech Systemics LLC` | 0.952 | Initech Systems LLC |
| `Globex Ashore Inc` | 0.876 | Globex Offshore Inc |
| `Acme Shelling Co` | 0.815 | Acme Shell LLC |
| `Robert Rowe` | 0.798 | Robert Roe |
| `Umbrella Insurance Group` | 0.743 | Umbrella Holdings Group |

Two (0.966) are false positives at *every* threshold below 0.966 — no usable threshold sheds
them. This is the precision cost of the deployed matcher, contained (not eliminated) by the
REVIEW cap: a semantic hit is capped to human review (`NAME_MATCH_CAP=60`), so these become
reviewer load, not auto-rejections. On this synthetic set that is 7/16 hard negatives; the real
false-positive *rate* depends on how often such near-duplicate names occur in real traffic, which
this set cannot estimate.

## The blind-spot finding

> **The 27-case evaluation set contained no append cases of any semantic distance. The sweep
> endorsed 0.72. Adversarial testing then defeated 0.72 with a five-character append. The
> evaluation set had a blind spot, and the sweep could not have found it.**

Every positive in the set is a *bounded* legitimate variation — word substitution
(`Globex Overseas Inc`), suffix expansion (`Acme Shell Limited Liability Company`), word-order
swap (`Shell Acme LLC`), nickname (`Bob Roe`), dropped initial (`Mary Sample`). Not one positive
appends distant tokens to a listed name. So the sweep measured how well the matcher tolerates
*legitimate* variation and nothing about how it withstands *dilution*. A threshold that looks
excellent here (recall 1.00) is defeated in production by `"<listed name> " + 5 distant tokens`
(2.0c: cosine drops to 0.51–0.61, below 0.72). **An evaluation set that omits the adversary's
move cannot score a defense against it — the number it produces is precise and irrelevant.**

## Also unflattering: no adversarial robustness over difflib

> **The semantic layer provides tolerance to legitimate name variation. It provides no
> adversarial robustness over difflib: both fall to the same append.**

- *Legitimate-variation tolerance (real value).* On the 10 positives, semantic recall is
  **1.00** at 0.72. Several of these defeat the fuzzy `difflib` layer (0.90 ratio): word-order
  swap, suffix expansion, and nickname variants sit well below 0.90 fuzzy but 0.83–0.96 cosine.
  So embeddings genuinely add recall on *honest* variation — that is what the layer buys.
- *Adversarial robustness (none, over difflib).* 2.0c measured a 5-token adversarial append
  against `Globex Offshore Inc`: **fuzzy 0.487 (< 0.90, evades) AND semantic 0.506 (< 0.72,
  evades)** — both layers fall at the *same* 5 tokens (`docs/evidence/matcher_evasion.md`, §a/b).
  The embedding layer does not raise the adversarial bar above the string layer; a dilution
  append defeats both. The semantic net's value is entirely on the legitimate-variation axis,
  and zero on the adversarial axis.

## Threshold sweep (live Titan, 27 cases)

| thresh | TP | FN | FP | TN | precision | recall | F1 | FPR | tgt_acc |
|---|---|---|---|---|---|---|---|---|---|
| 0.60 | 10 | 0 | 4 | 13 | 0.714 | 1.000 | 0.833 | 0.235 | 1.00 |
| 0.64 | 10 | 0 | 3 | 14 | 0.769 | 1.000 | 0.870 | 0.176 | 1.00 |
| 0.68 | 10 | 0 | 2 | 15 | 0.833 | 1.000 | 0.909 | 0.118 | 1.00 |
| 0.70 | 10 | 0 | 2 | 15 | 0.833 | 1.000 | 0.909 | 0.118 | 1.00 |
| **0.72 (deployed)** | **10** | **0** | **2** | **15** | **0.833** | **1.000** | **0.909** | **0.118** | **1.00** |
| 0.74 | 10 | 0 | 2 | 15 | 0.833 | 1.000 | 0.909 | 0.118 | 1.00 |
| 0.76 | 10 | 0 | 1 | 16 | 0.909 | 1.000 | 0.952 | 0.059 | 1.00 |
| 0.80 | 10 | 0 | 1 | 16 | 0.909 | 1.000 | 0.952 | 0.059 | 1.00 |
| 0.84 | 9 | 1 | 1 | 16 | 0.900 | 0.900 | 0.900 | 0.059 | 1.00 |
| 0.88 | 7 | 3 | 1 | 16 | 0.875 | 0.700 | 0.778 | 0.059 | 1.00 |

The two false positives at 0.72 are hard negatives: `Initech Solutions LLC` (0.966 — a
persistent FP at *every* threshold, genuinely confusable) and `Umbrella Insurance Group`
(0.743 — drops to a true negative at 0.76). `target_accuracy` is 1.00 throughout: when a
positive is flagged, it matches the *correct* listed entity, not a spurious one.

## Justification for the deployed 0.72 — stated honestly

On this set, **0.72 is not the F1-optimal threshold — 0.76–0.80 is** (F1 0.952 vs 0.909, same
perfect recall, one fewer false positive). The case for 0.72 over 0.76 is therefore *not* made
by this eval; it rests on a prior: **for a Do Not Pay screening control, a false positive is
cheap (a human reviews a clean payment) and a false negative is expensive (a listed entity is
paid), so bias toward recall and accept the extra review load.** 0.72 sits at the low end of the
recall-1.00 plateau, buying the widest sensitivity margin before recall degrades (it starts
falling at 0.84). That is a defensible *design* rationale — but note the eval cannot confirm the
margin it buys, because **every threshold from 0.60 to 0.80 has recall 1.00**: the set has no
positive near the decision boundary, so it cannot show 0.72 catching something 0.76 misses.
Two blind spots compound: no near-boundary positives, and no append cases at all. **The
deployed 0.72 is a reasonable recall-leaning prior that this evaluation neither confirms nor,
more importantly, stress-tests.**

## Stability

`--stability` embeds the full set twice and reports max per-dimension drift:
**max abs drift = 0.00e+00** across two independent passes. Titan v2 with `normalize:true`
returns bitwise-identical vectors for identical input, so the matcher is fully deterministic —
no threshold flicker from embedding nondeterminism. (Caveat: determinism is not robustness; a
deterministic matcher that is deterministically wrong on appends is still wrong.)

## Cost (measured, `scripts/measure_bedrock_cost.py`)

| item | rate | per 1000 payments |
|---|---|---|
| Titan embed (per payee) | ~5 tokens ≈ **$0.0000001 / call** (~$0.10 / million) | worst case 1 call each → **$0.0001 / 1000** |
| Nova Lite brief (advisory, on-demand) | ~241 in / 85 out tok ≈ **$0.000035 / brief** | n/a (only generated when a reviewer opens a case) |

The semantic net fires **only when the exact/fuzzy string layers miss** (`app.py:175`), so the
$0.0001/1000 is a worst case (all payments reaching the net). **Dollars are not the constraint**
— the operative cost is latency (one Bedrock round-trip per net-reaching payment). Full rates in
`docs/BEDROCK_COST.md`.

## Validity limitation (stated, not buried)

**The evaluation set is synthetic, and I wrote both the perturbations and the matcher.** The 27
cases are hand-authored variants of a small seed list, not sampled from real payment traffic or
a real adversary. The positives encode *my* notion of "legitimate variation"; the hard negatives
encode *my* notion of "confusable." A matcher tuned by the same author against the same author's
set will look good — that circularity is exactly how the append blind spot survived until
adversarial testing hit it from outside. These numbers bound the matcher's behavior *on this
set*; they do not generalize to production traffic, and 2.4 expands the set specifically to
close the append blind spot this report names.

## 2.4 outcome — recall reported per class, never blended

The set was expanded 27 → 62 (append positives — adversarial/benign/numeric; legit-suffix
positives; high-overlap hard negatives) and the identical sweep re-run
(`docs/evidence/semantic_eval_results_v2.json`; construction in `docs/sme/SEMANTIC_EVAL.md` §9).

**A single blended recall figure ("1.000 → 0.484") is not a before/after — the matcher did not
change; the case-mix did.** That number is a function of how many append cases I chose to add,
not a property of Component B. Report the two classes separately (recall at 0.72):

| positive class | what it tests | recall @ 0.72 |
|---|---|---|
| **benign-variation** (word sub, suffix expansion, nickname — what the layer is for) | honest name drift | **10/10 = 1.00** |
| **append-class** (name + distant/legit-suffix tokens) | dilution | **5/21 = 0.24** |

The benign-variation recall is unchanged from the 27-case run — the semantic layer does exactly
its job on honest variation. The append-class recall is low because, per the geometry finding
above, diluted names land in the hard-negative band. **These are two different questions and must
not be averaged into one recall.** (The blended 0.484 across all 31 positives is reported only as
an aside; its value moves with the positive/append ratio, which is an authoring choice.)

### Conditioned on what the deployed system actually screens (C2)

10 of the 15 rejected positives exceed 35 chars, so 2.1e refuses them at intake (400) — they
**never reach the matcher**, and counting them as matcher false negatives conflates the intake
layer with the matching layer. **Matcher recall on positives that PASS validation (≤35 ASCII —
the deployed system): 10/16 = 0.625** (benign 9/9 = 1.00; append **1/7 = 0.14**). The
pre-validation figure — all 31 positives, **15/31 = 0.484** — is **historical** (it describes the
matcher before 2.1e, screening inputs the deployed system now rejects). Cite 0.625/benign-append
split for the deployed system; cite 0.484 only as the pre-validation baseline.

**No threshold recovers the append recall** (recall peaks 0.839 at 0.60, FPR 0.323, still 5 FN)
— because, again, the diluted cosines sit inside the hard-negative band, not because of the
threshold. The ≤35 append residual (6 of the 16 reaching positives) is the windowed backstop's
target; input validation removes the >35 subset but cannot help the in-budget residual.

> **One benign casualty of the cap:** `Acme Shell Limited Liability Company` (36 chars) is a
> *legitimate* suffix-expansion variant — a benign positive — yet it exceeds 35 and is rejected
> at intake. So the cap's false-reject cost lands on honest variation too, not only on attackers
> (see C3/C4).
