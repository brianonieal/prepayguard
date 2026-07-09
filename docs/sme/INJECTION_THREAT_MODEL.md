# Injection and matcher-evasion threat model

**Date:** 2026-07-09. Grounds every claim in a file:line citation or a named evidence
file. Evidence: `docs/evidence/injection_trials.md` (live prompt-injection trials),
`docs/evidence/matcher_evasion.md` + `matcher_evasion_data.json` +
`matcher_evasion_distance_data.json` (offline matcher quantification).

## Scope and the corrected framing

Two models sit in this system, with opposite trust properties:

- The **generative** model (Nova Lite adjudication brief) is advisory. It has no
  disposition path and never enters the audit record. Proven at runtime
  (`injection_trials.md`, all trials: `audit_has_brief_field: False`).
- The **embedding** model (Titan) is IN the disposition path: `_semantic_match` emits a
  cosine-derived `confidence` into `matches[]` (`src/component_b_enrichment/app.py:152-154`)
  and C reads `matches[]` (`src/component_c_risk_scoring/app.py:38`). Its failure mode is a
  **false negative**, which in a Do Not Pay system means the payment goes out.

So the primary risk is an integrity failure of the screening control (embedding + the
string layers), not the brief.

## Attack surface: attacker-controlled fields reaching a model

The payee name is the attacker-controlled field. It reaches two models:

1. **Payee to the embedding matcher.** `_embed(payment.get("payee"))`
   (`component_b_enrichment/app.py:140`), cosined against reference vectors (`:146`),
   emitting a match (`:152-154`). This feeds the disposition.
2. **Payee to the brief.** `_llm_brief` builds `facts["payee"]` from
   `record["payment"]["payee"]` (`src/console_api/app.py:177`) and serializes it into the
   Bedrock `converse` user message (`:188-189`). This is advisory only.

Enumerated other model inputs, none independently attacker-controlled beyond the payee:
`facts` also carries `disposition`, `risk_score`, `reasons`, `matches`, `amount`,
`reference_list_version` (`console_api/app.py:174-184`); `reasons`/`matches` are derived
by C/B from the payee, and `amount` is a number validated at intake
(`api_intake_stage/main.tf:231-235`). Component G embeds reference entries
(`component_g_refresher/app.py:53`), which come from SAM, not from the payer. So the payee
is the single attacker-controlled free-text field reaching a model.

## 2.1a verification of the correctness claim (blocking for F1)

The 2.0c write-up asserted that legitimate payment records "routinely carry
distant-but-legitimate content in the payee NAME field." Verified against the actual
formats:

- **PrePayGuard's own schema:** `payee` is a single free-text `string`, `minLength 1`, no
  `maxLength`, no `pattern`, no separate address or remittance fields
  (`api_intake_stage/main.tf:222-238`). The intake handler adds no payee validation
  (`component_a_intake/app.py`, `_extract_payment` checks only `payment_id`). PrePayGuard's
  own sample data and generator never place c/o, Attn, DBA, or remittance content in the
  payee (`docs/sample-data/sample_payments.csv`, `scripts/gen_sample_payments.py`; grep for
  those tokens returns nothing).
- **Real federal disbursement formats separate and constrain the name field:**
  - NACHA ACH: the Individual/Company Name field is a **22-character** legal-name field
    (positions 55-76); remittance goes in **separate addenda records** (Nacha ACH file
    details).
  - Fedwire: tag {4200} beneficiary is **structured** (identifier, account, name element);
    lines are **~35 characters**; remittance and reference data (invoice, loan, project
    numbers) go in **separate** Originator-to-Beneficiary lines, not the name.
  - Treasury Fiscal Service PAM Standard Payment Request (SPR 5.0.2) is a **fielded**
    file format with distinct payment-detail fields, not free text.

**Verdict: (ii).** Real formats separate name from address from remittance and bound the
name length to 22 to 35 characters. Legitimate ingestion that mirrors these formats would
place only a short, clean legal name in `payee`, and a short clean name does not dilute.
The 2.0c "legitimate records carry distant content in the name field" claim is **not
supported**. The correctness angle is therefore a **Component A input-validation defect**:
A accepts unconstrained free text where a length-bounded structured name belongs. The
honest-data false negative arises only if ingestion maps address or remittance content
into `payee`, or accepts unbounded free text (which A does). F1 is rated on the
adversarial path, with the correctness path scoped as a Component A finding, not an
inherent property of legitimate data.

## 2.1b Does evasion survive a bounded name field? (blocking; full evidence in `matcher_evasion_bounded.md`)

Verdict (ii) makes input validation at Component A the candidate remediation only if the
attack dies under a realistic cap. Measured against the same 5 real SAM entities from 2.0c,
live Titan, payee cosined vs the actual stored v4 vector
(`docs/evidence/matcher_evasion_bounded.md`, `matcher_evasion_bounded_data.json`):

- **A length cap NARROWS F1; it does not close it.** At Fedwire 35, a fitting distant token
  (`OK PAY`, `FY26Q3`, `ZX QQ`, all ≤7 chars) still evades all three layers for **3 of 5**
  entities — every listed name short enough to leave budget. At NACHA 22 it survives for
  **2 of 5** (the short names with ≥7 chars of slack). It dies only for names that already
  ~fill the field (both 31-char names) or where the budget is too tight (James at 22, 3
  chars).
- **Homoglyph / transliteration inside the name (zero budget → immune to any cap)** evades.
  A 2-char mixed-script homoglyph (`Наwwk LLC` → cosine 0.519) evades for short names, and
  **2.1d shows a full Cyrillic transliteration is single-script and evades all 5** (cosine
  0.11–0.29, fuzzy 0). So a **single-script-consistency rule does NOT close this class** — only
  an **ASCII / Latin-script restriction** does, at the cost of rejecting legitimate diacritic
  names (`José Muñoz`). A length cap is powerless against it regardless.
- **Punctuation/whitespace padding does NOT evade** — `_normalize_name` strips it and the
  exact layer re-matches.
- **Trailing truncation to 35 is not a fix**: it restores the match only for suffix-placed
  fillers on long names; prefix/infix placement (front-loading the filler) defeats it for
  all 5 entities (cosine 0.02–0.07 for prefix).
- **2.1d residual, concrete (all 96 live v4 entries, real Titan): 75 of 96 (78%) remain
  evadable via a fitting short append under a 35-char cap; 31 of 96 (32%) under 22** — plus the
  length-independent transliteration class. The cap is a necessary narrowing, not a closure.
- **2.1d — the cap's own false-negative cost:** 29/96 names exceed 22 chars, 11/96 exceed 35.
  A **truncating** cap makes 8/96 (at 22) or 2/96 (at 35) listed entities a **full screening
  miss** (a false-NEGATIVE the cap itself introduces); a **rejecting** cap (the 2.1e design)
  avoids that but bounces those legit long names (fail-closed availability cost). 35 is chosen
  over 22 to minimize both (see DECISIONS entry).

Consequence for remediation: input validation (maxLength **+ character class**, sized to the
rail) is the correct **primary** fix, but the two halves do very different amounts of work.
**The character-class rule is the load-bearing control, not the length cap:** the printable-
ASCII pattern (`^[ -~]+$`) closes the **entire** transliteration/homoglyph class (Cyrillic and
fullwidth are not printable ASCII — 2.1d(a)), while the 35-char cap closes only **~22% of the
append class** (21/96 entities lack the budget; **75/96 stay evadable**). And because the
control **rejects (400), it does not truncate**, the cap's cost is a legit-reject, not a
screening miss: **35 chars → 11/96 legit names rejected, 78% evadable; 22 chars → 29/96
rejected, 32% evadable** (verified vs the histogram). So input validation narrows F1 modestly
and repairs the input contract, but a **large residual remains**, which is where a robust
(windowed) matcher is the backstop. The character-class control is a **tradeoff (single-script
insufficient; ASCII-only closes the class but rejects diacritics), not a clean win** — both
variants are in the remediation table.

## 2.1c Attacker model (blocking)

Who can write `payee`? The intake POST is `authorization = "AWS_IAM"` (SigV4, DEC-5;
`api_intake_stage/main.tf:245`), so a write requires valid SigV4 credentials for an IAM
principal permitted to invoke the API (the payment-submitter role). There is no anonymous
write path. The request model accepts `payee` as `{type: string, minLength: 1}` with
`additionalProperties: true` and **no `maxLength`, no `pattern`**
(`api_intake_stage/main.tf:222-238`); the handler validates only `payment_id`
(`component_a_intake/app.py:74-77`). So any authorized submitter can place arbitrary free
text (any length, any script) in `payee`.

| # | Attacker | Can write distant tokens into `payee`? | Likelihood of F1 via this actor |
|---|---|---|---|
| AM1 | External actor with **stolen IAM credentials** for a submitter role | Yes, once credentials are held | **Low–Medium.** Gated by SigV4; requires a credential compromise first. Not the cheap path. |
| AM2 | **Compromised or malicious upstream** disbursing system (legitimate submitter role, turned hostile) | Yes, directly | **Medium.** Requires that one integrated system be subverted or insider-operated. Plausible but not trivial. |
| AM3 | **Fraudulent payee via an HONEST upstream** — the payee's own name/record flows through an unmodified disbursing system into `payee` | **This is the constrained, realistic case — see below** | **This is the one that decides F1's likelihood.** |

**AM3 is the realistic actor and the one the HIGH rating must rest on.** The question is
what constrains the name a fraudulent-but-registered payee can get into `payee` through an
honest pipeline:

- If the honest upstream mirrors a **real federal rail** (NACHA 22 / Fedwire 35, name field
  separated from address/remittance — verdict (ii)), the payee can only supply a **short,
  bounded, structured legal name**. Per 2.1b, that closes the append vector for long names
  but **leaves a residual for short registered names**, and a payee could plausibly register
  a short name or DBA containing a distant token. **Open question:** whether a real vendor
  registration (SAM, or a payer's vendor master) permits a legal name / DBA carrying escrow,
  "c/o", or admin tokens — **PrePayGuard has no DBA or "doing business as" field anywhere**
  (grepped: none in `src/`, `modules/`, schema), so any such content would have to ride
  inside `payee` free text, which only an upstream that maps it there would produce. I can
  verify PrePayGuard's schema and the absence of a DBA surface; I **cannot** verify what an
  arbitrary agency's real vendor-registration or ERP name field permits — mark that as open.
- If the honest upstream is **PrePayGuard's own unconstrained schema** (`payee` free text, no
  cap, `additionalProperties: true`), AM3 has the **full** surface: any length, any script,
  including the homoglyph class. This is the Component A defect, not a property of legitimate
  federal data.

**Re-rated F1 likelihood (impact stays HIGH — an improper payment is released):**

- Against the **as-built** system (unconstrained `payee`): **HIGH.** AM2 and AM3 both have a
  cheap path; 5 distant tokens or 2 homoglyph chars suffice, no credential theft required
  beyond the normal submitter role.
- Against a system that **mirrors a real rail** (bounded, character-class-clean name):
  **MEDIUM, residual.** The append vector is closed for long names; a residual persists for
  short registered names (2.1b) and depends on the open registration question above.

The HIGH rating is therefore a property of the **as-built unconstrained schema**, and input
validation is what moves it toward MEDIUM-residual — which is exactly why it leads the
remediation ordering below.

## Findings, rated separately

### F1. Matcher evasion (integrity failure of the screening control) - HIGH

The three name-matching layers share one primitive: they compare the WHOLE payee string
to the WHOLE reference name. Exact `payee == entry_name` (`component_b_enrichment/app.py:169`),
fuzzy `SequenceMatcher(...).ratio() >= 0.90` (`:45,171`), semantic `_embed(payee)` cosine
`>= 0.72` (`:123-127,140-152`). Appending text defeats the shared primitive:

- Fuzzy falls below 0.90 at any 5-token append (`matcher_evasion.md`, section b).
- Exact falls on any append (`:169`).
- Semantic falls whenever the appended text is embedding-distant from a company name;
  measured across 5 distance classes at a fixed 5 tokens, 4 of 5 evade, generalizing
  across 5 real SAM entities (`matcher_evasion.md`, 2.0c (a) and (d)).

Precondition: TIN-absent payments are accepted (`api_intake_stage/main.tf:231`;
`_extract_payment`). The reject band (score >= 80) can only be reached by an UNCAPPED TIN
match; name/fuzzy/semantic hits are capped at 60 by `NAME_MATCH_CAP`
(`component_c_risk_scoring/app.py:27,45-50`) and land in review at most. **Therefore
against an adversary who omits their TIN, the reject band never fires and the name matcher
is the sole operative control, and that control is defeated by about 5 distant tokens.**
Result: empty `matches[]`, C scores 0, disposition `approve` (`:56-63`); a listed Do Not
Pay entity is paid with no human review.

CI4A: **Integrity** (the screening control produces a false negative), with a secondary
**Availability**-of-control aspect (the control fails to protect). Likelihood HIGH (cheap,
5 tokens, no auth beyond the submitter role which any provisioned agency system holds).
Impact HIGH (improper payment released, the exact harm the system exists to prevent).

### F2. Brief poisoning, reject band - LOW

Demonstrated (trials 2 and 4, `injection_trials.md`): the brief recommended APPROVE on a
payment C rejected at 95. CI4A: **Integrity** of an advisory artifact. Impact LOW: the
payment is already blocked by C (`disposition: reject`), no human acts on the brief for a
rejected payment, and the brief never enters the audit (`_brief` returns an HTTP body
only, `console_api/app.py:195-204`; D writes the audit before any brief exists,
`component_d_disposition/app.py:173`). Likelihood HIGH (trivial), impact LOW.

### F3. Brief poisoning, review band - NOT DEMONSTRATED (do not upgrade a negative)

Across five review-band payloads (`injection_trials.md`, Phase 2.0b review-band section),
the three that actually landed in review held at INVESTIGATE; the brief did not flip to
APPROVE. This is a NEGATIVE result, not proof of safety. Its limits: one model
(`amazon.nova-lite-v1:0`), temperature 0.2, five payloads, one target entity. Partial
mitigation exists in the UI: the brief renders directly below the evidence panel and the
"Why score N -> band" explainer, same view, on-demand and labeled with model and timestamp
(`console/src/screens/AuditDetail.jsx:68,71,81,99,104,112`), so a reviewer sees the
contradicting evidence adjacent to any APPROVE prose. CI4A: **Integrity** of advisory
output and **Accountability** of the human decision. Likelihood UNKNOWN (not demonstrated),
impact MEDIUM if it occurs (a human could release a flagged payment). Residual: open; a
stronger model or phrasing, or a reviewer who reads the brief before the evidence, could
be misled.

### F4. Missing in-handler authorization on `_brief` and `_audit` - MEDIUM (from 2.6)

`GET /reviews/{id}/brief` (`console_api/app.py:895-896`, `_brief` `:195`) and
`GET /audit/{id}` (`:885`, `_load_audit`/return `:154-158`) perform NO in-handler
authorization. Admin-gated routes call `_is_admin` (`:69`, e.g. `:410,514,565,578,845`);
these two do not. Access control for them rests solely on the API Gateway resource policy
at the edge. CI4A: **Authorization** (no defense in depth), secondary **Confidentiality**
(audit records and briefs, which contain payee, amount, matches, and the model brief, are
exposed if the single edge control is ever misconfigured). This is a defense-in-depth
finding, not a live breach: the edge policy currently restricts invoke to the console
roles. See "Authorization finding" below. Not fixed; requires a decision.

### F5. Matcher FALSE POSITIVES on legitimate look-alike names - MEDIUM

The same whole-string embedding primitive that fails as a false NEGATIVE under dilution (F1)
fails as a false POSITIVE on genuinely different but surface-similar names. Measured on the
62-case eval (`EVAL_REPORT.md`, `semantic_eval_results_v2.json`): **7 of 16 hard negatives score
≥ 0.72 at the deployed threshold and are flagged as matches to a *different* listed entity** —
`Initech Solutions LLC` → Initech Systems LLC (**0.966**), `Globex Onshore Inc` → Globex Offshore
Inc (**0.966**), `Initech Systemics LLC` (0.952), `Globex Ashore Inc` (0.876), `Acme Shelling Co`
(0.815), `Robert Rowe` (0.798), `Umbrella Insurance Group` (0.743). **The two at 0.966 are false
positives at *every* threshold below 0.966** — no usable threshold sheds them, because (per the
EVAL_REPORT geometry finding) the append-positive and hard-negative distributions overlap and
there is no separating `t`. So F1 (false negative, dilution) and F5 (false positive, look-alike)
are two faces of one defect: whole-string cosine matching cannot both admit diluted true matches
and reject similar non-matches. CI4A: **Integrity** of the screening output (a clean payee wrongly
flagged). Likelihood depends on how often near-duplicate corporate/person names occur in real
traffic (this synthetic set cannot estimate the real rate); impact is bounded — a semantic hit is
capped to **REVIEW** by `NAME_MATCH_CAP=60` (`component_c_risk_scoring/app.py:27,50`; DEC-14), so
these become reviewer load, not wrong auto-rejections. **Contained, not eliminated.** The
robust-matcher follow-on (windowed / entity-resolution) is the fix for both F1 and F5.

## CI4A summary map

| Finding | Confidentiality | Integrity | Authentication | Authorization | Availability | Accountability |
|---|---|---|---|---|---|---|
| F1 matcher evasion | - | PRIMARY | - | - | control fails | - |
| F2 reject-band brief | - | advisory | - | - | - | - |
| F3 review-band brief | - | advisory | - | - | - | decision |
| F4 no in-handler authz | if edge fails | - | - | PRIMARY | - | - |
| F5 look-alike false positive | - | PRIMARY (clean payee flagged) | - | - | - | - |

## Risk-rating table

| # | Finding | Likelihood | Impact | Rating | Mitigation in place | Residual |
|---|---|---|---|---|---|---|
| F1 | Matcher evasion (embedding+fuzzy+exact, TIN-absent) | High (as-built, AM2/AM3); Medium-residual if rail-bounded (2.1b/2.1c) | High | **HIGH** | None on the matcher. C's cap only affects matched payments, not evaded ones. Input validation at A narrows, does not close (2.1b/2.1d). | Full as-built. Under a 35-char cap: **75/96 (78%) listed entities remain evadable** via a fitting short append, **plus the whole full-script transliteration class** (2.1d). Open. |
| F2 | Brief poisoning, reject band | High | Low | **LOW** | C already rejects; brief is advisory and non-audit. | Negligible: no human acts on a rejected payment's brief. |
| F3 | Brief poisoning, review band | Unknown (not shown) | Medium | **MEDIUM (open)** | UI adjacency of evidence and brief (`AuditDetail.jsx:71,81,99`); brief on-demand and labeled. | A stronger model/phrasing could flip it; reviewer-trust dependent. Open. |
| F4 | No in-handler authz on brief/audit | Low (edge holds) | Medium | **MEDIUM** | API Gateway resource policy restricts invoke to console roles. | Single control; a misconfig exposes audit/brief data. Open. |
| F5 | Look-alike false positives (whole-string cosine) | Unknown rate (synthetic set) | Medium | **MEDIUM** | `NAME_MATCH_CAP=60` caps a semantic hit to REVIEW, so a false positive is reviewer load, not a wrong auto-reject. | **7/16 hard negatives ≥0.72 on the eval; two at 0.966 unsheddable at any threshold** (`EVAL_REPORT.md`). Same whole-string defect as F1; robust-matcher follow-on fixes both. Open. |

## Root cause (state it plainly)

**PrePayGuard's intake schema accepted unbounded free text where every real federal
disbursement rail (NACHA ACH 22-char, Fedwire 35-char, Treasury PAM fielded) delivers a
bounded, structured name with address and remittance in separate fields.** `payee` is
`{type: string, minLength: 1}`, no `maxLength`, no `pattern`, `additionalProperties: true`
(`api_intake_stage/main.tf:222-238`), and the handler checks only `payment_id`
(`component_a_intake/app.py:74-77`). **That is the root cause.** The matcher behaved
**correctly given its input**: comparing a whole diluted string to a whole reference name is
a defensible design for a field that is supposed to contain a clean bounded name; the defect
is that Component A never enforced that the field contains one. The remediation ordering
below follows from this: fix the input contract first, harden the matcher for the residual.

## Remediation options (reordered per 2.1b/2.1c/2.1d; option 1 IMPLEMENTED in 2.1e, rest are options)

Each notes cost, what it breaks, residual, and its effect on the false-ACCEPT vs
false-REJECT tradeoff framed in `scripts/eval_semantic_matching.py` (precision/recall
sweep). "false accept" = a listed entity passes (misses); "false reject" = a clean payee
is flagged. **Ordering rationale:** 2.1b/2.1d show the attack dies under a rail-sized cap only
for names that ~fill the field, so input validation at Component A is the primary fix; a large
residual survives (75/96 under a 35-char cap, plus the full transliteration class), so windowed
matching stays the residual backstop; truncation is demoted because 2.1b shows placement
defeats it.

1. **[PRIMARY — implemented in 2.1e, flag-gated default ON] Length cap AND character-class
   validation at Component A intake.** Bound `payee` to the rail size and restrict its
   character class at the schema (`api_intake_stage/main.tf` model) and the handler
   (`_extract_payment`), returning **400 fail-closed** (an unvalidated payment is never
   screened, never approved). Cost: small. **Cap choice (35 vs 22) — on rejection grounds
   (the control rejects, it does not truncate, so there is no screening-miss cost):** verified
   vs the 96-entry histogram, **35 chars rejects 11/96 legit names and leaves 75/96 (78%)
   evadable; 22 chars rejects 29/96 and leaves 31/96 (32%) evadable.** **35 (Fedwire) chosen**
   on usability grounds (11 legit 400s vs 29), explicitly accepting that **78% of the list
   stays evadable** — the length cap is the minor control here. **The heavy lifting is the
   character-class rule, which is a tradeoff, NOT a clean win (2.1d(a)):**
   - A **single-script-consistency** rule is **insufficient** — a full Cyrillic transliteration
     is single-script and evades all 5 (cosine 0.11–0.29).
   - **ASCII-printable-only** closes the transliteration/homoglyph/fullwidth class but **rejects
     every legitimate diacritic name** (`José Muñoz`, `François`) — a real false-reject on the
     **payee stream** (the rule screens incoming payees, not the reference list; the reference
     list being all-ASCII is irrelevant to this cost, C3). Cost unquantified — no real payee-name
     distribution.
   - **Latin-script-only (allow diacritics)** is the lower-false-reject middle ground but needs
     NFKC folding to also stop fullwidth and is more complex.
   2.1e implements **ASCII-printable-only** (the version 2.1d shows is necessary to close the
   class) and documents the diacritic false-reject as a KNOWN LIMITATION with the Latin-script
   alternative noted. **Residual after this fix (measured, 2.1d): 75/96 (78%) listed entities
   remain evadable via an in-budget short append.** So this repairs the input contract and
   closes the transliteration class, but does **not** close F1 — it is the front line, not the
   whole fix.
   **⚠ The cap also degrades screening of long listed entities (C4/C6).** 11/96 reference names
   exceed 35 chars; a payment to those entities cannot carry the full name, so the matcher screens
   whatever ≤35 form the payer submits against the full stored name. Measured (real Titan,
   `matcher_evasion_bounded.md` §f), three consequences that belong together:
   1. **Exact and fuzzy both fail under the cap → semantic is the sole matching control.** For the
      realistic short forms a payer types (abbreviation, distinctive tail), **8 of the 11** long
      entities match *only* via semantic (exact never fires except one punctuation-heavy name;
      fuzzy ≥0.90 fires mainly on an *unrealistic* mechanical first-35 truncation of names barely
      over the cap). **Exactly 1 of the 11** (`SCIENTIFIC AND PRODUCTION ASSOCIATION OF MEASURING
      TECHNOLOGY`) is unmatchable by *any* of the three forms → auto-approved. The other 2 match
      on a realistic fuzzy form.
   2. **That semantic control is itself defeated by a further in-budget append** (2.4): a payer/
      attacker who submits a matching ≤35 core and then dilutes it within the 35-char budget
      evades the one layer holding up long-entity screening.
   3. **Even when semantic catches a short form, the result is REVIEW, never REJECT.** Every name
      match — exact, fuzzy, and semantic — is capped below the reject threshold by
      `NAME_MATCH_CAP=60` (`component_c_risk_scoring/app.py:27,45-50`; DEC-14), so under the cap a
      long listed entity reaches at most human review, and **only a volunteered matching TIN can
      auto-reject it.** Without the cap it would reliably reach review via an *exact* match on its
      full name; the cap degrades that to "review only if a short form semantically matches, else
      auto-approve."
   So option 1 trades an evasion narrowing for **both** a false-REJECT cost (long legit names
   400'd — incl. the benign variant `Acme Shell Limited Liability Company`) **and** a degraded
   long-entity path (semantic-only, append-defeatable, review-capped, 1/11 unscreenable). This is
   a consequence of the remediation, not a footnote.
2. **[RESIDUAL BACKSTOP] Windowed / n-gram semantic matching.** Slide a window over the
   (now bounded) payee, embed each window, take the max cosine per reference entry. A short
   distant token cannot dilute a window it does not overlap, so this catches the residual
   that the cap leaves for short listed names. Cost: O(windows) embedding calls per payment
   (see build estimate). Breaks: nothing functionally; raises Bedrock cost and latency, and
   the eval re-sweep (2.3/2.4) must quantify a possible false-positive cost (a short clean
   window spuriously matching a short reference name). Residual: character-level perturbation
   of the name itself is a separate class — but note it is **already closed by option 1's
   character-class rule**, so with 1 in place windowing's residual is small. Tradeoff:
   reduces false-accept on the short-name residual with little false-reject change.
   **Addresses the shared whole-string PRIMITIVE, but only needed for the residual once
   option 1 bounds the input.** Not to be implemented now (per instruction).
3. **Require TIN, or route TIN-absent payments to review by policy.** If TIN is required,
   the reject band can fire; if TIN-absent payments are policy-routed to review, an evaded
   name at least reaches a human. Cost: small (schema + a C/D rule). Breaks: legitimate
   TIN-absent payments (foreign payees without a US TIN) are all forced to review, raising
   reviewer load. Residual: does not fix the matcher; it changes the failure from
   auto-approve to human review. Tradeoff: strongly reduces false-accept for the omit-TIN
   attack at the cost of a large false-reject (review) increase. Complementary to option 1
   (defense in depth on the TIN-absent precondition).
4. **Entity-name extraction before matching.** Strip suffixes, addresses, and prose to
   isolate the legal entity name, then match that. Cost: a real NLP/parsing component (new
   dependency or model). Breaks: parser errors mis-extract and either miss or over-flag.
   Residual: extraction is itself attackable and imperfect. Tradeoff: can reduce both false
   directions if accurate, but adds a new failure mode. Highest build cost. Largely
   subsumed by option 1 once the input is bounded and structured.
5. **Payee truncation before embedding (DEMOTED).** Truncate `payee` to the first N chars
   before matching. 2.1b shows this is **defeated by placement**: trailing truncation
   restores the match only for suffix-placed fillers on long names; prefix/infix placement
   (front-loading the filler) evades all 5 entities after truncation. Keep only as a
   normalization nicety, not a control. Addresses a symptom (length) and not even that
   reliably.
6. **Lower the semantic threshold below 0.72.** Accept more matches. Cost: config. Breaks:
   more clean payees flagged. Residual: dilution still drives the payee below any fixed
   threshold once the appended text is distant enough, so a lower threshold buys margin but
   not immunity. Tradeoff: directly trades more false-reject for less false-accept, the
   axis `eval_semantic_matching.py` already sweeps; the 2.0c/2.1b data show evaded payloads
   sit at cosine ~0.44 to 0.69, so the threshold would have to drop very low (with a large
   false-reject cost) to catch them.

The build estimate for the windowed backstop (option 2) is in the separate estimate section
below.

## Prior art (this is a known class, not novel)

Name-screening evasion is a well-documented attack class in sanctions and OFAC compliance:
sanctioned parties use name variations, transliterations, DBAs, and suffix differences to
avoid exact-match screening, and fuzzy and phonetic matching (Soundex, Jaro-Winkler) are
the standard defenses (OFAC Sanctions List Search tool documentation; AML watchlist
screening literature). What this threat model adds is not the class but the measurement:
a demonstration that an embedding-based matcher at a fixed 0.72 threshold is defeated by
about 5 embedding-distant tokens, quantified against real listed entities, and that the
evasion is distance-driven rather than adversarial-specific. Frame accordingly: a known
evasion class, measured against this system's embedding matcher.

## Authorization finding write-up (2.6, not fixed)

**Finding:** `_brief` and the audit-read path have no in-handler authorization; only the
edge (API Gateway resource policy) gates them. `console_api/app.py` gates admin routes
with `_is_admin` (`:69`, used at `:410,514,565,578,845`) and analytics with
`_is_admin_or_auditor` (`:622`), but `GET /reviews/{id}/brief` (`:895`) and
`GET /audit/{id}` (`:885`) call `_brief`/`_load_audit` directly with no identity check.

**Module 9 / CI4A:** an Authorization (broken access control) defense-in-depth gap, with a
Confidentiality consequence if the edge control fails (audit records and briefs contain
payee, amount, matches, disposition, and the generated brief). It is not a live breach: the
resource policy restricts invoke to the console roles, so unauthenticated access is blocked
today. It is single-layer.

**Defense-in-depth recommendation (not applied, pending your decision):** add an
in-handler role assertion on the brief and audit reads, mirroring the existing
`_is_admin_or_auditor` pattern, so authorization does not rest on the edge alone. I have
NOT implemented this; per instruction, a fix needs your go-ahead.

---

# Build estimate: windowed / n-gram semantic matching (option 2, the residual backstop), NOT implemented

Estimate only, per request. Behind an env flag `SEMANTIC_WINDOWED`, default OFF. Slide a
window over the payee, embed each window, take the max cosine per reference entry.
Appended distant text cannot dilute a window it does not overlap.

## Files touched and lines changed (estimate)

| File | Change | Est. lines |
|---|---|---|
| `src/component_b_enrichment/app.py` | `_windows(payee, size, stride, cap)` helper + a windowed branch in `_semantic_match` gated on `os.environ.get("SEMANTIC_WINDOWED")`; default path unchanged | ~30-45 |
| `environments/dev/main.tf` | add `SEMANTIC_WINDOWED = "false"` to the enrichment stage env (alongside `SEMANTIC_THRESHOLD` at :390-391) | ~1-2 |
| `tests/test_enrichment.py` | windowed-match unit tests + an evasion-resistance test (append 5 distant tokens, assert still matches with the flag on) | ~30-50 |
| `foundation/DECISIONS.md` | one decision record (windowed matcher, flag, cost, tradeoff) | ~15 |
| `scripts/eval_semantic_matching.py` | a `--windowed` mode so the sweep can score the windowed matcher | ~15-30 |
| **Total** | across 5 files | **~90-140** |

No new infra resources; no new IAM (same Bedrock InvokeModel the enrichment role already
holds). The change is contained to Component B plus config and tests.

## New Bedrock calls per payment

Today: **1** Titan embed call per payment, and ONLY when the string layers miss
(`_semantic_match` runs only if `not matches`, `app.py:175`). Cosine is in-memory against
the stored reference vectors (no per-entry Bedrock call).

Windowed: **up to MAX_WINDOWS embed calls per payment** (a cap, e.g. 8), still only when
the string layers miss. Each window is short (window size W tokens), so total input tokens
are roughly `min(windows, cap) * W`, comparable to or below embedding the whole payee.

## Cost delta per 1000 payments (from measure_bedrock_cost.py rates)

Titan is $0.00002 / 1K input tokens; a ~5-token payee embed is ~$0.0000001
(`BEDROCK_COST.md`). Worst case, the semantic net fires on all 1000 payments:

- Today: 1000 x 1 call x ~$0.0000001 ~= **$0.0001 per 1000** (~$0.10 / million).
- Windowed, cap 8: 1000 x up to 8 calls x ~$0.0000001 ~= **$0.0008 per 1000** (~$0.80 /
  million). Delta ~= **+$0.0007 per 1000 payments**, about 8x, still fractions of a cent.

**Dollars are not the constraint.** The real cost is **latency**: N Bedrock calls per
payment. At ~50-150 ms per embed, 8 sequential calls add ~0.4-1.2 s per payment on the
semantic path. Mitigations (parallelize the window embeds, or use Titan batch) are extra
work not costed here. Confirm the exact delta by running `scripts/measure_bedrock_cost.py`
against the windowed path once built (I have not, since it is not built).

## What the eval re-sweep requires (2.3/2.4, not done here)

- Add append-case classes to the eval set (2.4): noise-appended positives (they SHOULD
  match), legitimate-suffix positives, hard negatives with high lexical overlap.
- Run `eval_semantic_matching.py --windowed` and compare precision/recall/F1/FPR to the
  whole-string matcher at 0.72.
- The KEY new question windowing raises: **false positives.** A short window of a long
  CLEAN payee could spuriously match a short reference name, so windowing may trade
  restored recall (on diluted positives) for lower precision (more false flags). The
  re-sweep must measure that tradeoff and may require a separate windowed threshold. This
  is the analysis that decides whether windowing is safe to enable, and it is not a
  code-only task.

## Is a flag-gated fix a one-day job?

- The flag-gated CODE (B windowed branch + flag + unit tests + one-line TF + DEC entry):
  approximately **half a day to one day**.
- The EVALUATION needed to trust turning the flag on (expand the eval set per 2.4, re-sweep
  windowed vs whole-string, quantify the false-positive tradeoff, possibly retune a
  windowed threshold): approximately another **half day to a full day**.

So: implementing the flag-gated fix is roughly a one-day job; being able to responsibly
recommend enabling it is closer to **1.5 to 2 days** including the eval. The code alone
does not establish that windowing does not degrade precision; only the re-sweep does.
