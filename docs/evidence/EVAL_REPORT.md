# Semantic matcher evaluation report (Phase 2.3 — course objective 5)

**Date:** 2026-07-09. **Method:** live `amazon.titan-embed-text-v2:0` (us-east-2), the
deployed matcher's own `best_match` logic (`scripts/eval_semantic_matching.py`, which imports
Component B's cosine). 27-case set (`scripts/semantic_eval_set.json`): 10 positives (legit name
variants that SHOULD match a listed entity), 10 clean, 7 hard negatives. Raw results:
`docs/evidence/semantic_eval_results.json`. Reproduce:
`python scripts/eval_semantic_matching.py --stability --json docs/evidence/semantic_eval_results.json`.

## The strongest finding: it is the embedding geometry, not a threshold, and not my case-mix

> **Diluted-name vectors fall inside the hard-negative cosine band. No threshold separates an
> append-class positive from a genuinely different similar name — this is a property of the
> embedding space, not of how many append cases I chose to add.**

Measured on the expanded set (§2.4, `semantic_eval_results_v2.json`): the 21 append-class
positives span cosine **0.499–0.882**; the 16 hard negatives span **0.351–0.966**. **All 21/21
append positives sit inside the hard-negative band**, and only 1 of 21 reaches the *lowest*
benign-variation positive (0.831). Benign-variation positives, by contrast, occupy a tight high
band **0.831–0.963**, cleanly above the hard negatives. So a threshold low enough to admit the
diluted names (≈0.50) also admits nearly every hard negative (precision collapses); a threshold
that keeps precision (≈0.72) misses the diluted names. There is no separating threshold because
Titan places a listed name diluted by distant tokens in the same region as a *different* company
sharing a token. **This claim does not depend on the case-mix**: adding or removing append cases
changes the recall *number*, but the overlap of the two cosine distributions is a fixed property
of the geometry. That is why 2.4's threshold sweep found no better threshold, and why input
validation (bound the string before it is embedded) — not re-tuning — is the lever.

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
