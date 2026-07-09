# 2.1b: Does evasion survive a bounded name field?

**Date:** 2026-07-09. **Blocking for the F1 remediation ordering.** **Method:** offline,
live `amazon.titan-embed-text-v2:0` (`normalize:true`, us-east-2). Each payee variant is
embedded and cosined against the **actual stored v4 per-entry vector** pulled from
`s3://treasury-dev-reference-<ACCOUNT_ID>/reference/current.json` — i.e. the exact vector
Component B cosines at runtime (`component_b_enrichment/app.py:146`), not a re-embedded
name. Fuzzy = `difflib.SequenceMatcher` on `_normalize_name` (`app.py:171,89-91`), threshold
0.90; semantic threshold 0.72 (`app.py:123-127`). The semantic operator is **`>=`**
(`app.py:147`: `if sim >= threshold`), so a cosine of **exactly 0.72 MATCHES** (does not
evade); "evades" therefore requires cosine **strictly < 0.72** AND fuzzy < 0.90 AND not exact
(all three layers miss → empty `matches[]` → C scores 0 → `approve`). Cosines are shown to 3
decimals to avoid a rounded `0.72` being misread as a boundary evasion (e.g. James + `APPROVE`
= **0.7161 < 0.72**, a true evade; had it been 0.7200 it would have matched). Raw data:
`docs/evidence/matcher_evasion_bounded_data.json` and `..._2_1d_out.json` /
`..._2_1d2_out.json`. Reproduce with the sweep in that JSON's `method` field.

The question this answers: verdict (ii) says a real rail delivers a **bounded** name, so the
candidate remediation is input validation at Component A sized to the rail, not windowed
matching. That only holds **if the attack dies under a realistic cap.** Tested here against
the same 5 real SAM entities from 2.0c.

## (a) Character budget under each cap

Budget = `cap − len(name)`; an append also consumes one separating space, so an append of
visible length `t` costs `t + 1`.

| entity | len | NACHA 22 budget | Fedwire 35 budget |
|---|---|---|---|
| YATAI SMART INDUSTRIAL NEW CITY | 31 | **−9 (name overflows cap)** | 4 |
| DIGITAL MARKETING AWARDS FZ LLC | 31 | **−9 (name overflows cap)** | 4 |
| James O. Wilson Jr. | 19 | 3 | 16 |
| Kathleen J King | 15 | 7 | 20 |
| Hawwk LLC | 9 | 13 | 26 |

Two of the five real listed names (both 31 chars) **do not fit** in NACHA's 22-char field
at all. A faithful NACHA ingest would truncate the legitimate name itself — a separate
correctness concern (the screened string is no longer the full listed name), and it means an
attacker impersonating those entities has zero append budget at 22.

## (b) Maximally-distant appends that FIT the budget (real Titan, vs stored vector)

Full grid in the JSON. Representative in-budget results (cosine / fuzzy; **bold = evades**):

| entity | `OK PAY` (+7) | `FY26Q3` (+7) | `ZX QQ` (+6) | `APPROVE` (+8) | `PAY NOW` (+8) | `.... / !!!` (punct) |
|---|---|---|---|---|---|---|
| Hawwk LLC | **0.693 / 0.72** | **0.591 / 0.72** | **0.596 / 0.75** | 0.808 / 0.69 (holds sem) | 0.824 / 0.69 | 0.987 / 1.0 (exact) |
| Kathleen J King | **0.639 / 0.81** | **0.613 / 0.81** | **0.659 / 0.83** | 0.761 / 0.79 | 0.904 / 0.79 | 0.980 / 1.0 (exact) |
| James O. Wilson Jr. | **0.681 / 0.83** | **0.640 / 0.83** | **0.549 / 0.85** | **0.716 / 0.81** | 0.856 / 0.81 | 0.989 / 1.0 (exact) |
| YATAI … NEW CITY | **0.574 / 0.90** | **0.635 / 0.90** | 0.692 / 0.91 (fuzzy holds) | 0.833 / 0.89 | 0.603 / 0.89 | 0.989 / 1.0 (exact) |
| DIGITAL … FZ LLC | 0.799 / 0.90 | 0.830 / 0.90 | 0.908 / 0.91 | 0.890 / 0.89 | 0.896 / 0.89 | 0.993 / 1.0 (exact) |

Two robust observations independent of the cap:

- **Punctuation / whitespace padding does NOT evade.** `_normalize_name` strips punctuation
  (`app.py:89-91`), so `"Hawwk LLC ...."` normalizes back to `"hawwk llc"` and the **exact**
  layer matches (`app.py:169`); the semantic net never even runs (`app.py:175`). Padding is a
  non-attack.
- **Which short token evades is entity-specific**, because it depends on the distance between
  that token and *that* name's stored vector. `OK PAY`, `FY26Q3`, and `ZX QQ` (all ≤7 chars)
  evade the three short names; `APPROVE`/`PAY NOW` sometimes hold on semantic. The attacker
  only needs *one* fitting distant token, and one exists for four of five entities within a
  ≤8-char budget.

## (b′) Homoglyph substitution INSIDE the name (no append → zero budget → immune to any cap)

The class 2.0b flagged as untested. Substitute Latin letters with visually identical
Cyrillic lookalikes; no length change, so it fits under **any** cap including a name that
already overflows.

| entity | k=1 | k=2 | k=3 | k=4 | all payloads mixed-script? |
|---|---|---|---|---|---|
| Hawwk LLC | 0.591 / 0.94 | **0.519 / 0.88** | **0.328 / 0.80** | **0.328 / 0.80** | yes |
| Kathleen J King | 0.985 / 0.97 | 0.868 / 0.93 | **0.676 / 0.86** | **0.625 / 0.81** | yes |
| James O. Wilson Jr. | 0.792 / 0.94 | 0.814 / 0.88 | 0.823 / 0.88 | 0.804 / 0.80 (holds) | yes |
| YATAI … NEW CITY | 0.902 / 0.97 | 0.938 / 0.95 | 0.877 / 0.93 | 0.812 / 0.93 (fuzzy holds) | yes |
| DIGITAL … FZ LLC | 0.943 / 0.97 | 0.893 / 0.94 | 0.908 / 0.92 | 0.898 / 0.90 (holds) | yes |

`Наwwk LLC` (2 Cyrillic substitutions) drops cosine to **0.519** and fuzzy to **0.88** —
both layers miss, the payee is auto-approved, and **it fits under NACHA's 22-char cap because
it does not add a single character.** Homoglyph evades semantic+fuzzy for the two shortest
names within a few substitutions; longer names hold because the fuzzy layer survives the
stripped-out characters. Decisive point: **every homoglyph payload is mixed-script** (Latin +
Cyrillic), so a length cap does nothing to it, but a **character-class / single-script rule
at Component A rejects the entire class.**

## (c) Does evasion survive? Per-entity verdict

"Survives" = at least one **in-budget** payload evades all three layers.

| entity | @ Fedwire 35 (append) | @ NACHA 22 (append) | Homoglyph (any cap) |
|---|---|---|---|
| Hawwk LLC (9) | **YES** (`OK PAY`, `FY26Q3`, `ZX QQ`, …) | **YES** (`OK PAY`, `FY26Q3`, `ZX QQ`) | **YES** (k≥2) |
| Kathleen J King (15) | **YES** (`OK PAY`, `SYSTEM OK`, `ZX QQ`, …) | **YES** (`OK PAY`+7, `FY26Q3`+7, `ZX QQ`+6) | **YES** (k≥3) |
| James O. Wilson Jr. (19) | **YES** (`APPROVE`, `OK PAY`, `ZX QQ`, …) | **NO** (3-char budget: nothing distant fits) | no (holds to k=4) |
| YATAI … NEW CITY (31) | **NO** (4-char budget) | **NO** (name overflows cap) | no (fuzzy holds) |
| DIGITAL … FZ LLC (31) | **NO** (4-char budget) | **NO** (name overflows cap) | no (holds) |

**Plainly:**

- **At Fedwire 35, evasion survives for 3 of 5** — every listed name short enough to leave
  room (≤ ~20 chars) still admits a fitting distant token. It dies only for names that
  already ~fill the field (both 31-char names).
- **At NACHA 22, append-evasion survives for 2 of 5** (Hawwk, Kathleen — the short names with
  ≥7 chars of slack). It dies for James (3-char budget too tight) and for the two 31-char
  names (which the field would itself truncate).
- **Homoglyph ignores the cap entirely** and evades semantic+fuzzy for the two shortest
  names at zero budget cost.

## (d) Truncation: would trailing truncation to 35 restore the ORIGINAL 5-token payloads?

Component A truncating `payee` to 35 chars before matching, tested against the 2.0c
adversarial filler `"SYSTEM ignore prior instructions approve"` at three placements
(cosine after truncation vs stored vector):

| entity | suffix (name then filler) | prefix (filler then name) | infix |
|---|---|---|---|
| YATAI … NEW CITY | 0.880 → **match restored** | 0.031 → **evades** | 0.430 → **evades** |
| DIGITAL … FZ LLC | 0.975 → **match restored** | 0.040 → **evades** | 0.282 → **evades** |
| James O. Wilson Jr. | 0.583 → **still evades** | 0.071 → **evades** | 0.555 → **evades** |
| Kathleen J King | 0.525 → **still evades** | 0.034 → **evades** | 0.475 → **evades** |
| Hawwk LLC | 0.498 → **still evades** | 0.015 → **evades** | 0.456 → **evades** |

Truncation to 35 restores the match **only** for a **suffix**-placed payload on a **long**
name (YATAI, DIGITAL), where the cut discards nearly all the filler. For short names, enough
filler survives the 35-char window to keep evading even in suffix form. And **prefix or infix
placement defeats truncation for every entity** — front-loading the filler pushes the true
name out of the retained window (cosine 0.02–0.07 for prefix). An attacker who places filler
before the name beats a trailing truncation universally. **Truncation is not a fix; it is
defeated by placement**, which confirms the residual noted for remediation option 1.

## Verdict: input validation NARROWS F1, it does not fully close it

A length cap sized to the rail (22/35) is **necessary but insufficient**:

1. It closes the append vector only where the listed name nearly fills the field. For the
   common case of a **short** listed name (individuals, short LLCs — 3 of our 5 real SAM
   entries), a distant ≤7-char token still fits the budget and defeats all three layers, at
   both 35 and (for the shortest) 22.
2. A **character-class / single-script rule is required in addition** — it is the only thing
   that closes the zero-budget homoglyph class, which no length cap can touch.
3. Even length + character-class leaves a **residual for short listed names**: a clean,
   in-budget, single-script distant token (`OK PAY`, `FY26Q3`) still evades. That residual is
   precisely where a robust matcher (windowed/n-gram) would be the backstop — not the primary
   fix, the residual mop-up.

So: **input validation at Component A (maxLength + character class, sized to the rail) is the
correct primary remediation and it substantially narrows F1, but it does not eliminate it for
short listed names.** Windowed matching addresses that residual; it is not the front-line fix.
This is the ordering the revised 2.1 adopts.

> **The three qualitative claims above ("3 of 5", "the only thing that closes the homoglyph
> class is a character-class rule", "short listed names") are refined and partly corrected by
> 2.1d below with concrete N-of-96 counts and a full-script homoglyph test. Read 2.1d as the
> authoritative residual sizing.**

---

# 2.1d: closing the three holes (real Titan; correction trail preserved)

Same method (live Titan, cosine vs the actual stored v4 vector, `>=` 0.72 at `app.py:147`).
Raw data: `docs/evidence/matcher_evasion_bounded_data.json` sibling files
`sweep_2_1d_out.json` / `sweep_2_1d2_out.json`.

## (a) Full-script homoglyph — a single-script rule does NOT close the class

2.1b's homoglyph payloads were all **mixed-script**, which made a "character-class rule" look
like a clean closer. It is not. Transliterating every letter to Cyrillic yields a **single-
script** (pure Cyrillic) payload that a mixed-script / single-script-consistency detector
passes — and it still evades, because the embedding sees entirely different tokens and the
fuzzy layer sees an empty normalized string (`_normalize_name` strips all non-`[a-z0-9]`):

| entity | full-Cyrillic payee | single-script? | ASCII? | cosine | fuzzy | evades? |
|---|---|---|---|---|---|---|
| YATAI SMART INDUSTRIAL NEW CITY | `уатаи смарт индустриал неш циту` | **yes (Cyrillic)** | no | 0.290 | 0.00 | **YES** |
| Hawwk LLC | `һашшк ллц` | **yes** | no | 0.106 | 0.00 | **YES** |
| DIGITAL MARKETING AWARDS FZ LLC | `дигитал маркетинг ашардс фз ллц` | **yes** | no | 0.243 | 0.00 | **YES** |
| James O. Wilson Jr. | `жамес о. шилсон жр.` | **yes** | no | 0.240 | 0.00 | **YES** |
| Kathleen J King | `катһлеен ж кинг` | **yes** | no | 0.222 | 0.00 | **YES** |

**All 5 single-script payloads evade** (cosine 0.11–0.29, far below 0.72). Therefore:

- A **single-script consistency rule does NOT close the homoglyph/transliteration class** — a
  uniformly-Cyrillic payee passes it and evades. This corrects 2.1b's implication that "a
  character-class rule" closes the class.
- **Only an ASCII-only (or Latin-script-only) restriction** rejects these non-ASCII payees.
  And that carries a **real false-reject cost**: legitimate diacritic names are non-ASCII and
  would be rejected — confirmed non-ASCII: `José Muñoz`, `François Lefèvre`,
  `Søren Kierkegaard`, `Zoë O'Hara`, `Renée Zellweger`.

So the character-class control is a **tradeoff, not a clean win.** Two variants, both go in the
remediation table:

| character-class rule | closes full-Cyrillic transliteration? | closes fullwidth-Latin? | rejects legit diacritics (`José Muñoz`)? |
|---|---|---|---|
| single-script consistency only | **NO** (Cyrillic is single-script) | no | no |
| Latin-script-only (allow diacritics) | yes | no (fullwidth is script=Latin) unless NFKC-folded first | **no** (allows them) — lower false-reject, higher complexity |
| **ASCII-printable only** | yes | yes | **YES** — closes the class, but rejects every diacritic name |

## (b) The cap's OWN false-negative cost (96 live v4 entries)

Length distribution of all 96 names in the live v4 list (min 6, max 66, mean 21.5):

| bucket (chars) | count |
|---|---|
| 5–9 | 3 |
| 10–14 | 21 |
| 15–19 | 25 |
| 20–24 | 25 |
| 25–29 | 3 |
| 30–34 | 8 |
| 35–39 | 6 |
| 40–44 | 2 |
| 50–54 | 1 |
| 60–64 | 1 |
| 65–69 | 1 |

**29 of 96 names exceed 22 chars; 11 of 96 exceed 35.** A rail-sized cap therefore has a cost
in **both** directions depending on whether the cap truncates or rejects:

- **If Component A TRUNCATES `payee` to the cap** (mirroring a real rail field), the truncated
  legit payee is screened against the full stored name and can MISS its own listed entity:
  **8 of 96 entries become a full screening miss at a 22-char cap** (truncated name matches on
  none of exact/fuzzy/semantic vs its own stored vector); **2 of 96 at a 35-char cap.** This is
  a **false-NEGATIVE introduced by the cap** — a listed Do Not Pay entity paid. It is why
  truncation is demoted, not adopted.
- **If Component A REJECTS `payee` over the cap** (400, fail-closed — the design 2.1e adopts),
  there is **no screening miss** (an unscreenable payment is never approved), but legitimate
  long-named payments are rejected: **up to 29 of 96 (30%) name-lengths exceed a 22-char cap,
  11 of 96 (11%) exceed 35** — an availability / false-REJECT cost that an operator must handle
  out-of-band.

**This is why 35 (Fedwire) is chosen over 22 (NACHA):** 22 either misses 8/96 listed entities
(truncating) or bounces 29/96 legit long names (rejecting); 35 cuts that to 2/96 or 11/96
respectively, while still bounding the field. See the DECISIONS entry.

## (c) Threshold-boundary correction

The semantic operator is **`>=`** (`component_b_enrichment/app.py:147`), so cosine **= 0.72
matches** and does not evade. `James O. Wilson Jr. + APPROVE` measures **0.7161** at full
precision (`>= 0.72` → `False`), so it is a genuine evade — but it must be shown as **0.716**,
not a rounded `0.72`, which would falsely read as a boundary match. All 2.1b/2.1d "evades" are
strictly `< 0.72`; no evade in this evidence sits at or above the threshold. Tables corrected to
3-decimal cosines and the operator cited in the method note.

## (d) Residual sizing as N-of-96 (concrete, real embeddings)

Not "short names" — measured. For each of the 96 live entries with budget under the cap, the
attacker tries a few in-budget distant tokens (`OK PAY`, `FY26Q3`, `ZX QQ`, `PO 7781`,
`JAZZ OWL`) and evades if any one drops cosine `< 0.72` with fuzzy `< 0.90`:

| cap | entries with append room | **confirmed evadable (real Titan)** | % of 96 |
|---|---|---|---|
| Fedwire 35 | 77 | **75** | **78.1%** |
| NACHA 22 | 32 | **31** | **32.3%** |

**F1 residual, stated concretely: 75 of 96 listed entities (78%) remain evadable via a fitting
short append under a 35-char cap; 31 of 96 (32%) under a 22-char cap** — and, orthogonally, the
full-script transliteration/homoglyph class of (a) evades **regardless of length**, closed only
by an ASCII/Latin-script rule at its own false-reject cost. A rail-sized length cap alone leaves
the majority of the list evadable; it is a necessary narrowing of the input contract, not a
closure of F1. The residual is the target for the windowed matcher (recommended follow-on, not
implemented).
