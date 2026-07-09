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

## CI4A summary map

| Finding | Confidentiality | Integrity | Authentication | Authorization | Availability | Accountability |
|---|---|---|---|---|---|---|
| F1 matcher evasion | - | PRIMARY | - | - | control fails | - |
| F2 reject-band brief | - | advisory | - | - | - | - |
| F3 review-band brief | - | advisory | - | - | - | decision |
| F4 no in-handler authz | if edge fails | - | - | PRIMARY | - | - |

## Risk-rating table

| # | Finding | Likelihood | Impact | Rating | Mitigation in place | Residual |
|---|---|---|---|---|---|---|
| F1 | Matcher evasion (embedding+fuzzy+exact, TIN-absent) | High | High | **HIGH** | None on the matcher. C's cap only affects matched payments, not evaded ones. | Full: an evaded listed entity is auto-approved. Open. |
| F2 | Brief poisoning, reject band | High | Low | **LOW** | C already rejects; brief is advisory and non-audit. | Negligible: no human acts on a rejected payment's brief. |
| F3 | Brief poisoning, review band | Unknown (not shown) | Medium | **MEDIUM (open)** | UI adjacency of evidence and brief (`AuditDetail.jsx:71,81,99`); brief on-demand and labeled. | A stronger model/phrasing could flip it; reviewer-trust dependent. Open. |
| F4 | No in-handler authz on brief/audit | Low (edge holds) | Medium | **MEDIUM** | API Gateway resource policy restricts invoke to console roles. | Single control; a misconfig exposes audit/brief data. Open. |

## Remediation options (options only; not chosen, not implemented)

Each notes cost, what it breaks, residual, and its effect on the false-ACCEPT vs
false-REJECT tradeoff framed in `scripts/eval_semantic_matching.py` (precision/recall
sweep). "false accept" = a listed entity passes (misses); "false reject" = a clean payee
is flagged.

1. **Payee normalization / truncation before embedding.** Truncate the payee to the first
   K tokens (or the first N chars, mirroring the ACH 22-char / Fedwire 35-char name field)
   before matching. Cost: a few lines in B. Breaks: legitimate long-but-real names beyond
   K tokens lose their tail. Residual: an attacker front-loads the true name then appends
   after the cut; a naive char cap can be defeated by padding before the name. Tradeoff:
   reduces false-accept from dilution; small false-reject increase for genuinely long
   names. Addresses a symptom (length), not the whole-string primitive.
2. **Entity-name extraction before matching.** Strip suffixes, addresses, and prose to
   isolate the legal entity name, then match that. Cost: a real NLP/parsing component (new
   dependency or model). Breaks: parser errors mis-extract and either miss or over-flag.
   Residual: extraction is itself attackable and imperfect. Tradeoff: can reduce both false
   directions if accurate, but adds a new failure mode. Highest build cost.
3. **Windowed / n-gram semantic matching.** Slide a window over the payee, embed each
   window, take the max cosine per reference entry. Appended text cannot dilute a window it
   does not overlap. Cost: O(windows) embedding calls per payment (see build estimate).
   Breaks: nothing functionally; raises Bedrock cost and latency. Residual: character-level
   perturbation of the name itself (homoglyph, transliteration) is unaffected; that is a
   separate class. Tradeoff: reduces false-accept from dilution with little false-reject
   change, because a clean window still matches. **This is the only option that addresses
   the shared whole-string PRIMITIVE rather than a symptom.**
4. **Length cap and character-class validation at Component A intake.** Bound `payee`
   length and restrict character classes at the schema (`api_intake_stage/main.tf` model)
   and/or handler. Cost: small. Breaks: rejects legitimately long or non-Latin names if the
   bound is wrong. Residual: does not fix matching for content within the bound; an attacker
   fits the append inside the cap. Tradeoff: neutral to matching precision/recall; it
   shrinks the attack surface, it does not repair the matcher. This is the direct fix for
   the 2.1a Component A defect (unconstrained free text).
5. **Require TIN, or route TIN-absent payments to review by policy.** If TIN is required,
   the reject band can fire; if TIN-absent payments are policy-routed to review, an evaded
   name at least reaches a human. Cost: small (schema + a C/D rule). Breaks: legitimate
   TIN-absent payments (foreign payees without a US TIN) are all forced to review, raising
   reviewer load. Residual: does not fix the matcher; it changes the failure from
   auto-approve to human review. Tradeoff: strongly reduces false-accept for the omit-TIN
   attack at the cost of a large false-reject (review) increase.
6. **Lower the semantic threshold below 0.72.** Accept more matches. Cost: config. Breaks:
   more clean payees flagged. Residual: dilution still drives the payee below any fixed
   threshold once the appended text is distant enough, so a lower threshold buys margin but
   not immunity. Tradeoff: directly trades more false-reject for less false-accept, the
   axis `eval_semantic_matching.py` already sweeps; the 2.0c data shows evaded payloads sit
   at cosine 0.44 to 0.64, so the threshold would have to drop very low (with a large
   false-reject cost) to catch them.

The build estimate for option 3 is in the separate estimate section requested.

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

# Build estimate: windowed / n-gram semantic matching (option 3), NOT implemented

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
