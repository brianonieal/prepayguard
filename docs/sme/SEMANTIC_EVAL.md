# SEMANTIC_EVAL.md — measured evaluation of the semantic-matching layer

Course objective 5 (evaluate the LLM workflow on performance, stability, cost,
and human review). This converts PrePayGuard's one differentiating component from
asserted (DEC-19 cites an informal "clean ~0.24, variants 0.86 to 0.97" note) to
measured: precision, recall, F1, and false-positive rate across a threshold sweep,
on a labeled set, against real Bedrock Titan embeddings.

- Component under test: `src/component_b_enrichment/app.py` (`_semantic_match`,
  `_embed`, `_cosine`, `_semantic_threshold`).
- Model: `amazon.titan-embed-text-v2:0` (1024-dim, `normalize: true`), the exact
  id wired in `environments/dev/main.tf`.
- Harness: `scripts/eval_semantic_matching.py` (real Bedrock) reusing Component
  B's own `_embed` and `_cosine`; CI reproducibility test:
  `tests/test_semantic_eval.py` (deterministic, no Bedrock).
- Labeled set: `scripts/semantic_eval_set.json`. Raw results:
  `docs/sme/semantic_eval_results.json`.
- Run date: 2026-07-06, account <ACCOUNT_ID>, us-east-2.

## 1. Weakest-case-first (what this eval does NOT establish)

Lead with the case against over-reading these numbers:

- **The set is synthetic and small** (10 positive, 7 hard-negative, 10 clean = 27
  cases) built by the author, not a production sample. It measures whether Titan
  embeddings separate deliberate name variants from unrelated and surface-similar
  names on the repo's own synthetic list. It does not establish a production
  false-positive rate on real Do Not Pay data at volume.
- **No adversarial obfuscation.** The positives are ordinary real-world drift
  (abbreviation, word-order, suffix change, nickname). An adversary deliberately
  crafting a name to sit just under the cosine threshold (character insertion,
  homoglyphs, padding tokens) is not modeled and would likely evade the layer.
  Semantic matching is a net for honest variance, not an anti-evasion control.
- **English, Latin-script, entity-name-shaped inputs only.** Transliteration
  across scripts and non-Latin names are untested.
- **The layer only ever adds a REVIEW flag.** It cannot auto-approve or
  auto-reject (Component C caps a semantic hit to REVIEW). So this eval bounds two
  costs only: missed variants that slip to `approve` (false accept) and clean
  payees sent to a human (false reject). It says nothing about the string-rule or
  TIN paths, which are evaluated separately by `tests/test_enrichment.py`.

## 2. How the labeled set was built (so it is auditable, not cherry-picked)

Reference list = the 8-entry v1 bundled synthetic list (9000000xx TINs, invented
names). Every test payee is a name-only input, because semantic matching is
name-based and runs only when the TIN/exact/fuzzy string rules found nothing.

Three classes, each with a stated construction rule:

- **Positive (10)** — a name that refers to the SAME listed entity but that string
  matching misses: word substitution (Offshore to Overseas), legal-suffix change
  (LLC to Limited, LLC to Incorporated), word-order swap (Shell Acme LLC),
  abbreviation (Holding Grp), leading article (The Umbrella ...), dropped middle
  initial (Mary Sample), given-name nickname (Bob Roe). Each names the reference
  entity it should match, so we can check the match points at the RIGHT entity.
- **Hard negative (7)** — a DISTINCT entity whose surface overlaps a listed name:
  Acme Shield LLC vs Acme Shell LLC, Initech Solutions LLC vs Initech Systems LLC,
  Umbrella Insurance Group vs Umbrella Holdings Group, John Q Public Library vs the
  person John Q Public, etc. These should NOT match; they are where a similarity
  matcher is most likely to false-positive.
- **Clean (10)** — unrelated legitimate vendor names with no relation to the list.

Metric framing is the binary review decision the layer actually makes:

| | flagged (best cosine >= threshold) | not flagged |
|---|---|---|
| **positive** (should flag) | TP | FN = false ACCEPT (bad variant slips to approve) |
| **negative** (should not flag) | FP = false REJECT (clean payee to a human) | TN |

precision = TP/(TP+FP), recall = TP/(TP+FN), FPR = FP/(FP+TN),
F1 = harmonic mean. Target accuracy = of flagged positives, the fraction whose
single best match is the correct listed entity.

## 3. Per-case similarity (real Titan, 2026-07-06)

Best reference entity and cosine for each payee (full data in
`semantic_eval_results.json`):

```
positive       The Umbrella Holdings Group          -> Umbrella Holdings Group  0.963
positive       Initech Systems Limited              -> Initech Systems LLC      0.957
positive       Mary Sample                          -> Mary M Sample            0.945
positive       Umbrella Holding Grp                 -> Umbrella Holdings Group  0.938
positive       Acme Shell Limited Liability Company -> Acme Shell LLC           0.903
positive       Shell Acme LLC                       -> Acme Shell LLC           0.893
positive       Globex Overseas Inc                  -> Globex Offshore Inc      0.882
positive       Globex Overseas Incorporated         -> Globex Offshore Inc      0.857
positive       Initech System                       -> Initech Systems LLC      0.844
positive       Bob Roe                              -> Robert Roe               0.831   (lowest positive)
hard_negative  Initech Solutions LLC                -> Initech Systems LLC      0.966   (intrinsic FP)
hard_negative  Umbrella Insurance Group             -> Umbrella Holdings Group  0.743
hard_negative  Ace Shell LLC                        -> Acme Shell LLC           0.650
hard_negative  Acme Shield LLC                      -> Acme Shell LLC           0.637
hard_negative  Robert Doe                           -> Robert Roe               0.570
hard_negative  Globe Offset Inc                     -> Globex Offshore Inc      0.565
hard_negative  John Q Public Library                -> John Q Public            0.489
clean          (all 10)                             -> various                  0.131 - 0.222
```

The clean class tops out at 0.222, far under any usable threshold: unrelated
vendors are not a false-positive source. All the tension is in the hard negatives.

## 4. Threshold sweep (real Titan, 2026-07-06)

```
 thresh  TP  FN  FP  TN   prec  recall     F1    FPR  tgt_acc
-------------------------------------------------------------
   0.60  10   0   4  13  0.714   1.000  0.833  0.235     1.00
   0.64  10   0   3  14  0.769   1.000  0.870  0.176     1.00
   0.68  10   0   2  15  0.833   1.000  0.909  0.118     1.00
   0.70  10   0   2  15  0.833   1.000  0.909  0.118     1.00
   0.72  10   0   2  15  0.833   1.000  0.909  0.118     1.00   <- deployed default
   0.74  10   0   2  15  0.833   1.000  0.909  0.118     1.00
   0.76  10   0   1  16  0.909   1.000  0.952  0.059     1.00
   0.80  10   0   1  16  0.909   1.000  0.952  0.059     1.00
   0.84   9   1   1  16  0.900   0.900  0.900  0.059     1.00
   0.88   7   3   1  16  0.875   0.700  0.778  0.059     1.00
```

Reading it:

- **Recall is 1.000 all the way up to 0.80**, then falls (Bob Roe at 0.831 drops
  first at 0.84). Target accuracy is 1.00 throughout: every flagged positive
  matched the correct listed entity, never a different one.
- **Two false positives sit at the deployed 0.72**: `Initech Solutions LLC`
  (0.966) and `Umbrella Insurance Group` (0.743).
- `Umbrella Insurance Group` (0.743) is sheddable by raising to 0.76, which lifts
  precision to 0.909 and halves FPR to 0.059 with no recall loss on this set.
- `Initech Solutions LLC` (0.966) is NOT threshold-removable: it scores higher
  than 8 of the 10 true positives. No threshold that keeps recall usable can drop
  it. It is an intrinsic limit of name-only similarity (two real companies sharing
  a brand token and a legal suffix), and the correct handling is exactly what the
  system already does: cap it to human REVIEW, never auto-reject.

## 5. Recommended threshold: keep 0.72 (measured, not asserted)

Recommendation: **keep the versioned default at 0.72.** Reasoning, given the
cost asymmetry that a false accept (missed variant to `approve`) lets a bad
payment through while a false reject only spends reviewer time:

- 0.72 already achieves **recall 1.000** on this set, so lowering it buys no
  recall and only adds false rejects (0.60 adds two more FPs for nothing).
- Raising to 0.76 would improve precision on THIS set, but it shrinks the recall
  safety margin from 0.111 (0.831 lowest positive minus 0.72) to 0.071. Because
  false accepts are the costly error and real payee variants will be noisier than
  this clean synthetic set, spending recall margin to shed a single borderline
  false positive is the wrong trade. The one FP it would remove (Umbrella
  Insurance Group) is itself a defensible thing to put in front of a human.
- The remaining FP at 0.72 (Initech Solutions LLC) is intrinsic and is correctly
  contained by the REVIEW cap.

This measurement therefore CONFIRMS the DEC-19 default rather than moving it,
which is the honest outcome to report: 0.72 was a reasonable conservative pick and
the data backs it. The threshold is versioned per-list (`semantic_threshold` in
the reference document), so a larger or real list should re-run this harness and
re-tune; the sweep is the mechanism for doing that, not a one-time number.

## 6. Stability

`python scripts/eval_semantic_matching.py --stability` embeds the full set twice
and reports the maximum absolute per-dimension drift between the two passes:
**0.00e+00** on 2026-07-06. Titan Embed Text v2 is deterministic for a fixed model
version, so the cosine values, the sweep, and every metric above are exactly
reproducible. A model-version change (a new Titan minor) would require re-running
the sweep and re-versioning the threshold; the harness makes that a one-command
check.

## 7. Human-review and responsible-use posture

- The layer only routes to a human; Component C caps a semantic hit to REVIEW
  (`NAME_MATCH_CAP = 60`), so no payment is ever auto-rejected on an approximate
  name match. The human makes and owns the decision.
- The match is explainable: the audit record carries `matched_on: name_semantic`,
  the `similarity`, the matched `source`/`severity`, and the `reference_version`
  whose vectors it was judged against. No black box.
- A Bedrock outage degrades the net to rule-based screening rather than DLQ-ing
  the payment (measured behavior in `test_semantic_bedrock_error_degrades_not_dlq`).

## 8. Headline numbers (for the handoff)

On a 27-case labeled synthetic set at the deployed 0.72 cosine threshold, real
`amazon.titan-embed-text-v2:0` embeddings: **precision 0.83, recall 1.00, F1 0.91,
false-positive rate 0.12, target-entity accuracy 1.00, embeddings deterministic
(0.00 drift).** The two false positives are near-duplicate distinct entities where
routing to human review is defensible; one is intrinsic to name-only similarity
and is contained by the REVIEW cap. Cost of this evaluation run is measured in
`BEDROCK_COST.md`.
