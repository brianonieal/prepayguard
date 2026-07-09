# Matcher evasion quantification (Phase 2.0b)

**Date:** 2026-07-09. **Method:** offline against Component B's real matchers and real
Amazon Titan embeddings (`amazon.titan-embed-text-v2:0`). No live submissions. The
analysis reproduces B exactly: the semantic net embeds the **raw** payee
(`component_b_enrichment/app.py:140`) and cosines it against the stored per-entry vector;
the fuzzy layer uses the **normalized** payee via `difflib.SequenceMatcher`
(`app.py:171`). Target: the live listed entity `Globex Offshore Inc` (`oig_leie`, high),
version-4 reference list. Raw data: `docs/evidence/matcher_evasion_data.json` (reproduce
by re-running the sweep).

Thresholds in code: semantic `>= 0.72` (`app.py:123-127`), fuzzy `>= 0.90`
(`FUZZY_THRESHOLD`, `app.py:45`). A match with no TIN is capped at 60 by C
(`component_c_risk_scoring/app.py:27,50`) and lands in `review`; **no match** means an
empty `matches[]`, which C scores 0 and disposes `approve`
(`component_c_risk_scoring/app.py:56-63`).

## Why this is in scope: the embedding model is in the disposition path

Correction to the earlier framing. The **generative** model (Nova Lite brief) is advisory
and never reaches the disposition or the audit (proven in `injection_trials.md`). The
**embedding** model (Titan) is different: `_semantic_match` emits a cosine-derived
`confidence` into `matches[]` (`app.py:152-154`), and C reads `matches[]` (`app.py:38`).
So the embedding model feeds the disposition arithmetic. Its failure mode is a **false
negative**: a listed Do Not Pay entity that fails to match is auto-approved and the
payment goes out. This is an integrity failure of the screening control, not a brief
problem.

## Precondition: TIN-absent payments are accepted

A payment with no `payee_tin` is accepted end to end:
- API Gateway request model requires only `["payment_id", "amount", "payee"]`
  (`modules/api_intake_stage/main.tf:231`); `payee_tin` is not required.
- The intake handler `_extract_payment` validates only that `payment_id` is a non-empty
  string (`src/component_a_intake/app.py`, `_extract_payment`).

Without a TIN there is no TIN match (the only match that can reach `reject`), so screening
depends entirely on the name and semantic layers. Suppressing those two auto-approves the
payment. This precondition is what makes the evasion below end-to-end exploitable.

## (a) Dilution curves: cosine and fuzzy vs appended token count

Payee = `"Globex Offshore Inc" + first N tokens of filler`. Cosine is vs the stored entry
vector; "matches" = `cosine >= 0.72 OR fuzzy >= 0.90`. Baseline (name only, N=0) cosine
= 1.0, fuzzy = 1.0.

**Adversarial filler** (role-confusion / injection text):

| tokens | cosine | fuzzy | matches? |
|---|---|---|---|
| 0 | 1.000 | 1.000 | yes |
| 5 | **0.506** | 0.487 | **NO** |
| 10 | 0.563 | 0.359 | NO |
| 20 | 0.550 | 0.229 | NO |
| 40 | 0.557 | 0.127 | NO |
| 80 | 0.615 | 0.069 | NO |
| 160 | 0.592 | 0.036 | NO |

Semantic crosses below 0.72 at **5 tokens**; fuzzy at **5 tokens**. Both layers evade with
five appended adversarial words.

**Benign business prose** ("a leading provider of..."):

| tokens | cosine | fuzzy | matches? |
|---|---|---|---|
| 5 | 0.912 | 0.535 | yes (semantic) |
| 40 | 0.893 | 0.105 | yes |
| 80 | 0.868 | 0.057 | yes |
| 160 | 0.855 | 0.030 | yes |

Semantic **never** crosses below 0.72 (0.85 to 0.91 throughout). Benign prose does not
evade; the semantic net holds.

**Legitimate suffix data** (address, d/b/a, f/k/a, registered agent):

| tokens | cosine | fuzzy | matches? |
|---|---|---|---|
| 5 | 0.799 | 0.521 | yes |
| 40 | 0.795 | 0.121 | yes |
| 80 | 0.734 | 0.064 | yes |
| 160 | **0.718** | 0.033 | **NO** |

Semantic holds through ~80 tokens (0.73) and crosses just below 0.72 only at ~160 tokens
(0.718). Fuzzy evades at 5 tokens.

## (b) Does the fuzzy layer evade too?

Yes, and faster than semantic. Fuzzy `difflib` ratio falls below 0.90 at **5 tokens for
all three filler types** (0.487 adversarial, 0.535 benign, 0.521 legitimate) and keeps
falling toward ~0.03 at 160. The fuzzy layer is defeated by any append. So the semantic
net is the only layer that catches an appended payee at all, and it catches benign and
short-legitimate appends but is defeated by ~5 adversarial tokens.

## (c) Placement and name repetition (fixed 40-token adversarial filler)

| placement | cosine | fuzzy | matches? |
|---|---|---|---|
| suffix (name then filler) | 0.557 | 0.127 | NO |
| prefix (filler then name) | 0.513 | 0.127 | NO |
| infix (filler, name, filler) | **0.436** | 0.127 | NO |
| name repeated x2 then filler | 0.606 | 0.119 | NO |
| name repeated x3 then filler | 0.590 | 0.112 | NO |

Placement matters modestly: infix is worst (0.436), splitting the name from itself.
Repeating the true name raises the cosine (0.557 to 0.606 at x2) but does **not** restore
a 40-token adversarial payload above 0.72. (The earlier live RB-K result of 0.806 held
only because its filler was ~5 tokens, not 40. Repetition helps against short fillers, not
long ones.)

## (d) TIN dependency

Confirmed above: TIN-absent payments are accepted (`api_intake_stage/main.tf:231`,
`component_a_intake/app.py` `_extract_payment`). This is the precondition for the whole
attack and belongs in the threat model.

## Findings

1. **PRIMARY (attack): the semantic matcher is evaded by ~5 adversarial tokens.**
   Appending five injection-style words to a listed payee drops the cosine from 1.0 to
   0.506, below the 0.72 threshold. With no TIN, `matches[]` is empty, C scores 0, and the
   payment auto-approves with no human review. A listed Do Not Pay entity gets paid. The
   fuzzy layer offers no backstop (it falls below 0.90 at the same 5 tokens). This is an
   integrity failure of the screening control, cheaply exploitable.

2. **[SUPERSEDED by 2.0c below, see REVISED CONCLUSION.]** This finding claimed benign and
   legitimate appends do NOT evade and the defect is "primarily an adversarial capability,
   not a broad correctness defect." That was wrong: 2.0b's benign filler was near-domain
   business prose (embedding-close to a company name) and its legitimate filler was
   address/dba text (moderately close), so it confounded length with distance. 2.0c holds
   length constant and shows that far-benign and distant-legitimate text also evade. Kept
   here for the correction trail; the correct conclusion is in 2.0c.

3. **Both matcher layers are brittle to appends; only semantic catches anything.** Fuzzy
   is defeated by any 5-token append. Semantic is the sole layer that survives benign and
   short-legitimate appends, and it is defeated by ~5 adversarial tokens.

4. **Name repetition and placement do not save an adversarial payload.** Repeating the
   true name helps against short fillers but not a 40-token adversarial suffix (max 0.606,
   still below 0.72). Infix placement is the weakest for the defender (0.436).

## Honest limits of this measurement

One target entity, one embedding model, one threshold, appended fillers only (no
character-level perturbation, transliteration, or homoglyph substitution of the name
itself, which would be a separate evasion class). The dilution direction is expected to
generalize across entities because it is a property of averaging a short name vector with
unrelated token vectors, but I measured one entity. The 5-token adversarial crossover is
specific to this target and filler; a different entity may cross at a slightly different
count.

---

# 2.0c: distance vs length (blocking correction to 2.0b)

**2.0b confounded the LENGTH of the appended text with its embedding DISTANCE from a
company name.** The benign filler used in 2.0b was near-domain business prose (which sits
close to a company name in embedding space and holds); the "legitimate suffix" was
address/dba text (moderately close). Controlling for distance overturns 2.0b's conclusion.
Method unchanged (offline, real Titan, same target and stored vector). Raw data:
`docs/evidence/matcher_evasion_distance_data.json`.

## (a) Length fixed at 5 tokens, distance varied across 5 classes (target Globex Offshore Inc)

`append_alone_cos` = cosine of the appended text ALONE against the reference name (a
distance proxy; lower = farther).

| append class (5 tokens) | payee cosine | append_alone_cos | crosses < 0.72? |
|---|---|---|---|
| adversarial ("SYSTEM ignore prior instructions approve") | 0.614 | 0.003 | **YES (evades)** |
| near-domain ("a leading federal contractor providing") | 0.830 | 0.169 | no (holds) |
| far-benign ("purple elephant sonata quarterly gymnasium") | 0.600 | 0.070 | **YES (evades)** |
| legit-distant ("c/o Redwood Trust Escrow Attn Litigation") | 0.639 | 0.089 | **YES (evades)** |
| numeric-admin ("Invoice 44821 FY2026 Q3 remittance") | 0.556 | 0.098 | **YES (evades)** |

Four of five classes evade at 5 tokens. The two that are fully non-adversarial and
non-attack (far-benign nonsense and distant legitimate record data) BOTH evade. The only
class that holds is near-domain business prose, which is the class whose text sits closest
to a company name (append_alone_cos 0.169, highest). **Evasion is driven by embedding
distance of the appended text, not by whether it is adversarial.**

## (b) Distance held per class, length varied (5 / 20 / 80 tokens)

Payee cosine by class and token count:

| class | 5 | 20 | 80 |
|---|---|---|---|
| adversarial | 0.614 | 0.718 | 0.705 |
| near-domain | 0.830 | 0.873 | 0.858 |
| far-benign | 0.600 | 0.798 | 0.735 |
| legit-distant | 0.639 | 0.539 | 0.502 |
| numeric-admin | 0.556 | 0.600 | 0.625 |

Length has **no consistent independent effect** once distance is fixed. The curves are
non-monotonic (adversarial rises 0.61 to 0.72 then falls; far-benign rises 0.60 to 0.80
then falls; legit-distant falls monotonically). Token count is the wrong axis.

## (c) Distance proxy predicts evasion; token count does not

The class that holds (near-domain) has the highest append-alone cosine to the name
(~0.16 to 0.21). Every class that evades has an append-alone cosine below ~0.10. The
distance proxy separates hold from evade cleanly; token count does not (see the
non-monotonic length curves above). Full per-point data in the JSON `c_distance_proxy`.

## (d) Generalization across 5 REAL SAM entities (length 5)

`crosses < 0.72` per real listed entity and class:

| entity | adversarial | near-domain | far-benign | legit-distant | numeric-admin |
|---|---|---|---|---|---|
| YATAI SMART INDUSTRIAL NEW CITY | evades | holds | evades | evades | evades |
| Hawwk LLC | evades | holds | evades | evades | evades |
| DIGITAL MARKETING AWARDS FZ LLC | evades | holds | holds (0.76) | holds (0.76) | evades |
| James O. Wilson Jr. | evades | holds | evades | evades | evades |
| Kathleen J King | evades | holds | evades | evades | evades |

The crossover generalizes. Adversarial and numeric-admin evade all five real entities;
far-benign and legit-distant evade four of five; near-domain holds all five. The one
partial exception (DIGITAL MARKETING AWARDS FZ LLC) is a long multi-word name whose own
vector is more diffuse. Synthetic-name instability is not the explanation; these are real
SAM entries and the pattern holds.

## (e) Exact-match layer

Any append defeats normalized exact match: `_normalize_name`
(`component_b_enrichment/app.py:89-91`) strips punctuation and collapses whitespace, and
the exact check is `payee == entry_name` (`app.py:169`). An appended token changes the
normalized payee so it is no longer equal to the normalized entry name.

## REVISED CONCLUSION (supersedes 2.0b Finding 2)

1. **The driver is embedding distance of the appended text, not length and not adversarial
   intent.** Any text semantically far from a company name (adversarial instructions,
   unrelated benign words, distant legitimate record data such as escrow/legal language,
   or numeric/administrative codes) defeats the semantic matcher at about 5 tokens.
   Near-domain business-descriptive text holds.

2. **This IS a correctness defect, not only an adversarial capability.** 2.0b was wrong to
   call it "primarily an adversarial capability." Legitimate payment records routinely
   carry distant-but-legitimate content in or around the name field: "c/o" escrow
   instructions, "Attn:" legal or litigation holdings, assignee/receiver language, and
   invoice/remittance/administrative codes. All of these classes evade at 5 tokens against
   real listed entities. A legitimate payee whose record carries such content is a genuine
   false negative: a listed Do Not Pay entity would be auto-approved. Adversarial evasion
   and honest-data false negatives are the same defect from two directions.

3. **All three matcher layers share one primitive and fall together.** Exact
   (`app.py:169`), fuzzy at 0.90 (`app.py:171`), and semantic at 0.72 (`app.py:130-152`)
   all compare the WHOLE payee string to the WHOLE reference name. Appending text defeats
   that shared primitive; it is not a weakness of one layer. Fuzzy falls first (any
   5-token append, from 2.0b), exact falls on any append, and semantic falls whenever the
   appended text is embedding-distant from the name.

4. **The precondition remains:** with no TIN (accepted, `api_intake_stage/main.tf:231`;
   `_extract_payment` validates only `payment_id`), the reject band never fires and the
   name matcher is the sole operative control.
