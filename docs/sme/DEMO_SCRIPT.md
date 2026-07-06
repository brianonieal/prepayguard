# DEMO_SCRIPT.md: live demonstration runbook

For presenting PrePayGuard live to a Treasury executive and the capstone
professors. Time budget: about 10 minutes plus questions. The one hard safety
rule is in section 5; read it before you present.

Live URL: `https://d2rbxaf6pqgvb1.cloudfront.net` (verified serving 2026-07-06,
HTTP 200, login screen renders). Deployed image tag v3.2.1. Log in as the **admin**
user so the Overview, reference-data editor, analytics, and demo-reset controls are
all visible.

## 0. Before the room (2 minutes, off-screen)

- Confirm the site loads and you can sign in.
- Optional: run the admin demo-reset (Settings) so the dashboards start clean.
  This clears only the console-visible records; it never touches the immutable
  audit objects under Object Lock (that is the point, and a talking point).
- Have `docs/evidence/live_object_lock_proof.txt` open in a tab. You will SHOW
  immutability from this file; you will not perform it live (section 5).

## 1. The one sentence (say this first)

"PrePayGuard screens every payment against Do Not Pay sources before the money
goes out, decides approve, review, or reject with a written reason for each, and
records every decision in a vault that no one, including me, can ever alter or
delete."

That is the whole value proposition and a non-engineer executive can nod at it.

## 2. Prior-art armor (say it out loud, do not let them find it)

"This is not a claim to a new capability. It is an open, inspectable reproduction
of your own Do Not Pay program's decision logic. The gap it fills is transparency
and one measured component: a semantic name-matching layer that catches payee
variants exact and fuzzy string matching miss, and I can show you its measured
error rates, not just assert it works."

Leading with this removes the executive's strongest objection (that the novelty is
near-floor because Do Not Pay already exists) before it is raised. The honest edge
is execution quality, transparency, and the measured semantic layer.

## 3. The live end-to-end flow (about 4 minutes)

This is the real path proven live (`docs/evidence/console_live_e2e.txt`):

1. **Log in.** Cognito login gives temporary IAM credentials; the browser
   SigV4-signs every API call. No static keys in the browser. (One line: "the
   human console uses the same AWS identity model as the machine endpoints.")
2. **Submit a payment** to a clean payee. It auto-approves, score 0, reason "no
   reference-source matches." Show the audit record.
3. **Submit a flagged payee** using a REAL name from the live SAM.gov exclusions
   list, e.g. `YATAI SMART INDUSTRIAL NEW CITY` (pick any current entry from the
   admin Reference Data tab). It routes to **review**, score 60, reason "name_exact
   match on sam_exclusions", citing reference version 4. Say it out loud: "that is a
   real entry on the federal debarment list, not a synthetic one." (The old
   synthetic names Acme Shell LLC / Robert Roe were replaced by the real feed in
   v4, so do not use them.)
4. **Open the review queue**, open the case. Show score explainability, the cited
   **reference-list version**, and (optional) click the **AI brief** button; note
   in the UI it is labeled advisory and is never part of the audit record.
5. **Decide** (approve or reject). The decision writes its OWN audit record. Point
   out segregation of duties: the person who submitted a payment cannot decide it.
6. **Client-side integrity verify** on the audit detail: the browser recomputes the
   SHA-256 and shows the check mark. Immutability is clickable.

## 4. The differentiator (about 2 minutes, this is the memorable part)

Submit **"Globex Overseas Incorporated"** when the listed entity is **"Globex
Offshore Inc"**. Exact and fuzzy string matching miss it (difflib ~0.55). The
semantic layer flags it via Bedrock embeddings at cosine ~0.86 and routes it to
review, citing `matched_on: name_semantic` and the list version.

Then show the numbers (from `docs/sme/SEMANTIC_EVAL.md`): "On a labeled test set,
at the deployed threshold, this layer measured precision 0.83, recall 1.00, F1
0.91, and the embeddings are deterministic. Its false positives are near-duplicate
distinct entities, which is exactly why a semantic hit only ever routes to a human,
never auto-rejects." And the cost (from `docs/sme/BEDROCK_COST.md`): "the whole
demo's Bedrock cost is a fraction of a cent, and the architecture keeps the idle
baseline at about two dollars a month instead of the roughly seven hundred a
managed vector database would cost."

Optional: open the **Overview** tab, the executive showcase, for the disposition
mix, hit rate, and match-type charts over what the platform has actually processed.

## 5. IMMUTABILITY: show it, never perform it (the one hard rule)

Do **NOT** run any `terraform apply`, `aws s3 rm`, or retention change during the
demo. The audit bucket is S3 Object Lock in COMPLIANCE mode. Per DEC-4 and the
block in `environments/dev/terraform.tfvars`: retention on a written object cannot
be shortened or removed by any principal, including account root, and AWS Support
cannot override it. Setting `audit_retention_days` to a large value (and worse,
misreading the days-versus-years unit) on a real object during a live demo is
permanent and unfixable.

Instead, **show immutability from the captured proof**,
`docs/evidence/live_object_lock_proof.txt`: a real audit object where both a delete
and a shorten-retention attempt returned `AccessDenied` (verdict PASS). Say: "I
proved this once against the live bucket and captured it; I do not repeat it live,
because in COMPLIANCE mode the act of proving it is itself irreversible."

If asked to demonstrate it live, decline and explain why: a presenter who declines
to mutate a compliance store on request is showing the exact discipline the control
exists to enforce.

## 6. Close with residual risk and follow-on (about 1 minute, a graded objective)

Be the one to name the limits:

- **Reference data is synthetic** except where a real source is wired; false-
  positive and false-negative rates on production Do Not Pay feeds are not yet
  representative. The semantic eval is on a small synthetic set and does not cover
  adversarial name obfuscation.
- **Single account, single region, local Terraform state**: correct for a course
  prototype, not for production multi-operator or DR.
- **No load or chaos testing** yet; scaling and cold-start behavior are designed
  and configured but unmeasured under stress.

Follow-on (v0.2 direction): integrate the real restricted sources (SSA DMF, TOP,
OIG LEIE) behind proper record linkage and per-source threshold tuning; remote
Terraform state with locking; a materialized analytics rollup; load and DR testing;
and a Bedrock-availability alarm so a silent degradation of the semantic net is
observable. Every one of these is written up in the handoff, not discovered in the
room.

## Quick reference: what to have open

- Console (logged in as admin).
- `docs/evidence/live_object_lock_proof.txt` (immutability proof).
- `docs/sme/SEMANTIC_EVAL.md` (the measured numbers) and
  `docs/sme/BEDROCK_COST.md` (the cost line).
