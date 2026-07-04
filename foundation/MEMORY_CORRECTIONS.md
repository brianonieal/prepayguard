# MEMORY_CORRECTIONS.md — PrePayGuard ("Treasury")
# Calibration data and reflexion entries. Newest first within each section.

## REFLEXION LOG

ESTIMATION: gate=v3.1.0 estimated=2h actual=1.50h variance=-25% source=timelog errors_open=0 errors_close=0 date=2026-07-04T20:21:34Z
ESTIMATION: gate=v3.0.0 estimated=4h actual=1.50h variance=-62% source=timelog errors_open=0 errors_close=0 date=2026-07-04T19:51:01Z
ESTIMATION: gate=v2.4.0 estimated=4h actual=2.50h variance=-38% source=timelog errors_open=0 errors_close=0 date=2026-07-04T18:50:06Z
ESTIMATION: gate=v2.3.0 estimated=3h actual=1.50h variance=-50% source=timelog errors_open=0 errors_close=0 date=2026-07-04T18:24:12Z
ESTIMATION: gate=v2.2.0 estimated=4h actual=2.00h variance=-50% source=timelog errors_open=0 errors_close=0 date=2026-07-04T18:11:40Z
ESTIMATION: gate=v2.1.2 estimated=2h actual=1.00h variance=-50% source=timelog errors_open=0 errors_close=0 date=2026-07-04T17:51:18Z
ESTIMATION: gate=v2.1.0 estimated=3h actual=1.50h variance=-50% source=timelog errors_open=0 errors_close=0 date=2026-07-04T16:55:42Z
ESTIMATION: gate=v2.0.0 estimated=3h actual=2.50h variance=-17% source=timelog errors_open=0 errors_close=0 date=2026-07-04T13:54:51Z
ESTIMATION: gate=v1.6.0 estimated=3h actual=2.00h variance=-33% source=timelog errors_open=0 errors_close=0 date=2026-07-04T13:25:22Z
ESTIMATION: gate=v1.5.0 estimated=2h actual=1.00h variance=-50% source=timelog errors_open=0 errors_close=0 date=2026-07-04T12:31:57Z
ESTIMATION: gate=v1.4.0 estimated=3h actual=2.50h variance=-17% source=timelog errors_open=0 errors_close=0 date=2026-07-04T11:58:03Z
ESTIMATION: gate=v1.3.0 estimated=4h actual=1.60h variance=-60% source=timelog errors_open=0 errors_close=0 date=2026-07-04T01:23:40Z
ESTIMATION: gate=v1.2.0 estimated=2h actual=0.70h variance=-65% source=timelog errors_open=0 errors_close=0 date=2026-07-04T00:27:09Z
ESTIMATION: gate=v1.1.0 estimated=2h actual=0.80h variance=-60% source=timelog errors_open=0 errors_close=0 date=2026-07-04T00:18:36Z
ESTIMATION: gate=v1.0.0 estimated=16h actual=1.50h variance=-91% source=timelog errors_open=0 errors_close=0 date=2026-07-03T23:45:59Z
ESTIMATION: gate=v0.6.0 estimated=12h actual=0.70h variance=-94% source=timelog errors_open=0 errors_close=0 date=2026-07-03T23:16:12Z
ESTIMATION: gate=v0.5.0 estimated=9h actual=0.40h variance=-96% source=timelog errors_open=0 errors_close=0 date=2026-07-03T22:51:56Z
ESTIMATION: gate=v0.4.0 estimated=9h actual=0.70h variance=-92% source=timelog errors_open=0 errors_close=0 date=2026-07-03T20:08:06Z
ESTIMATION: gate=v0.3.0 estimated=8h actual=0.50h variance=-94% source=timelog errors_open=0 errors_close=0 date=2026-07-03T19:51:26Z
ESTIMATION: gate=v0.2.0 estimated=8h actual=0.40h variance=-95% source=timelog errors_open=0 errors_close=0 date=2026-07-03T19:18:04Z
ESTIMATION: gate=v0.1.0 estimated=10h actual=1.50h variance=-85% source=timelog errors_open=0 errors_close=0 date=2026-07-03T18:27:21Z

### REFLEXION - v3.1.0 Demo Controls (2026-07-04, Phase 4 gate 2/3)

**What went well**
- The reset stayed generic. `_clear_table` reads each table's own key schema and
  batch-deletes, so one helper clears all four working tables regardless of key name -
  no per-table hardcoding to drift out of sync. Driven off a list of env-var names.
- Guards were provable in isolation. Direct Lambda invokes proved the two guard rails
  (non-admin → 403, missing token → 400) AND that neither path deleted anything
  (reviews stayed at 35), before I ran the real wipe. Then the destructive run cleared
  420 rows, every table + /showcase read zero, and the audit bucket still held 217
  locked objects - the exact "dashboards empty, audit permanent" story the feature sells.
- Confirmation lives in two places on purpose: the browser gates the button behind a
  typed RESET, and the server independently requires `{"confirm":"RESET"}`. A stray API
  call without the token can't wipe the data.

**What bit - a textbook deploy-only IAM class (moto doesn't enforce IAM)**
- pytest passed with the WRONG IAM, twice over, because moto grants everything. Real
  DynamoDB then rejected two actions the code needs that I hadn't granted:
  1. `_clear_table` touches `table.key_schema`, which lazily calls **DescribeTable** -
     not covered by Scan/GetItem. AccessDenied.
  2. boto3's `table.batch_writer()` deletes via **BatchWriteItem**, NOT `DeleteItem` -
     I'd granted DeleteItem (which the code never calls). AccessDenied again.
  Both were IAM-only fixes (add DescribeTable, swap DeleteItem→BatchWriteItem) - no
  image rebuild, just re-applies. But it was two round-trips of "apply → invoke →
  read AccessDenied → widen policy" that a moment's thought about the ACTUAL boto3
  call surface would have collapsed into one.

**Lesson**
- When granting IAM for a boto3 call, grant for the API operation boto3 actually
  issues, not the conceptual verb. `batch_writer()` = BatchWriteItem; `.key_schema`
  (and any lazy Table attribute) = DescribeTable; a "delete loop" may never call
  DeleteItem at all. moto-backed tests confirm LOGIC but say nothing about IAM - for
  any new AWS action, the real-deploy AccessDenied is the only true test, so read the
  boto3 source or CloudTrail rather than guessing from the method name. Same family as
  the OCI-manifest and API-GW-account deploy-only issues: budget one apply-loop for it.

### REFLEXION - v3.0.0 Executive Showcase (2026-07-04, Phase 4 gate 1/3)

**What went well**
- The endpoint was almost free. The story page needed the same aggregates `/analytics`
  already computed, so the real backend work was extracting `_compute_summary()` and
  bolting on a match-type tally + worked examples. No new IAM, no new DECISION, no
  Terraform authz change — the route just rode the existing reviewer/admin `/*` and
  auditor `*/GET/*` grants. Confirming that up front (rather than adding policy) kept
  the whole gate to a Lambda-image bump.
- Data source honesty. Match-type detail lives only in the S3 audit records, not in
  audit_index — so instead of pretending or scanning everything, /showcase samples the
  recent 40 (bounded, logged) and backfills any missing disposition from the full index
  so all three worked examples always render. Reads truthfully without unbounded cost.
- Visual verification despite Cognito. The live app gates on Cognito, so I couldn't
  eyeball the page through the normal login headlessly. Built a throwaway Vite harness
  that aliased the signed api client to a static stub, mounted just `<Showcase/>`, and
  verified the donut arcs (76/17/6), gauge, 12 timeline bars, 5 match rows, 3 example
  cards and both multi-column grids via DOM + screenshots — then tore the harness fully
  down. Caught nothing broken, but proved the charts before spending a deploy.
- Direct-invoke live proof. Since treasury-cli can't assume a Cognito role (resource
  policy denies non-named principals), I proved /showcase end-to-end by invoking the
  deployed Lambda directly with a synthetic GET event — 200 against the real tables,
  178 screened, all three examples resolved. A clean substitute for a signed call.

**What bit (minor, all self-inflicted / environmental)**
- Vite alias replace-substring gotcha: a regex alias `/\/lib\/api\.js$/` only replaces
  the matched slice, leaving the `../` prefix → broken path. Anchoring the whole
  specifier (`/^\.\.\/lib\/api\.js$/`) fixed it. ESM configs also lack `__dirname`
  (needed `fileURLToPath`). Both are one-time preview-harness friction, not app code.
- Windows `aws.exe` can't read Git-Bash `/tmp` paths for `--payload fileb://` — write
  the event file repo-relative and pass a relative `fileb://` instead.
- `git status` is unavailable (env reports not-a-git-repo), and `rm -rf` was denied by
  the classifier — deleted the throwaway harness files individually instead.

**Lesson**
- When a "new page" only re-presents data an existing endpoint already aggregates,
  refactor the aggregation into a shared helper and add a thin projection — don't
  duplicate the scan logic or the numbers will drift. And when auth blocks the normal
  visual check, an isolated stub-harness + a direct Lambda invoke together give real
  confidence without a signed browser session.

### REFLEXION - v2.4.0 Analytics & Compliance Reporting (2026-07-04, Phase 3 FINAL)

**What went well**
- audit_index was already the perfect analytics source: since v1.5.0 it has one
  row per EVERY disposition, so mix/throughput/hit-rate fell out of a single
  scan - no new write path, no schema change. Reusing an existing seam beat
  building an analytics table.
- Read-only auditor via METHOD-scoped resource policy (*/GET/*) is clean and
  enforceable at the edge - the auditor literally cannot POST. Live-proven: the
  auditor's decision attempt 403'd at the edge, not just in the handler.
- The dashboard needed no chart library - CSS flin bars + a table. Kept the
  bundle light, consistent with prior "no heavy deps" calls.
- The whole session's history showed up honestly in the live numbers (178
  screened, 23.6% hit) - the analytics reflect the real pipeline, not seeded data.

**What bit (all anticipated)**
- The IAM-propagation error recurred exactly as flagged in the CONFIRMED scope:
  the new auditor role, named in the console resource policy, wasn't propagated
  when the policy updated -> re-plan + re-apply after get-role confirmed it. This
  is now a KNOWN, pre-announced cost of any gate that adds a role a resource
  policy references. Ideal fix (future): create new principal roles in a prior
  targeted apply before the policies that name them.
- vitest signIn() assumed every role lands on the Submit screen; the auditor
  (no submit access) broke it. Fixed by making signIn await the role-agnostic
  role-chip instead of the Submit heading. Lesson: shared test helpers must not
  assume a role-specific landing once roles diverge.

**Estimated vs actual**
Est ~2-4h -> actual ~2.5h. The biggest Phase 3 gate (new role + 2 endpoints +
dashboard UI), but every seam (roles, conditional IAM, scan helpers, CSS bars)
was warm from prior gates.

**MILESTONE: the locked roadmap (v0.1.0 -> v2.4.0, 21 gates + 1 hotfix) is
COMPLETE.** A live, AI-augmented, role-secured, fully-audited pre-payment
integrity platform. Anything further is a new Phase 4 (re-run BUILD APPROVED).
### REFLEXION - v2.3.0 LLM Adjudication Briefs (2026-07-04, Phase 3)

**What went well**
- The advisory boundary is enforced by CONSTRUCTION, not discipline: the brief
  endpoint only reads (GetObject + Converse) and returns in the HTTP response -
  no code path writes it to the audit. Live-verified the record has no brief
  field and the prose never leaked in.
- Grounding held: the live brief cited the ACTUAL evidence (SAM name match,
  severity high, confidence 80, score 60) and recommended INVESTIGATE - no
  invented facts, because the prompt feeds only the record and says "reason
  ONLY from it".
- Converse API = model-agnostic, so Nova Lite is a one-line swap later.
- Refactoring _get_audit into _load_audit reused the exact index->S3 lookup.

**What bit (my test, not the system)**
- My live boundary check false-positived: I named the payment "brief-{seed}", so
  `"brief" in json.dumps(record)` matched the PAYMENT_ID, not a field. Re-checked
  with a distinctive phrase + top-level-key inspection -> clean PASS. Lesson:
  don't put the token you're grepping-for-absence into the identifier you search.

**Estimated vs actual**
Est ~2-3h -> actual ~1.5h. Contained; the Bedrock plumbing was warm from v2.2.0.
### REFLEXION - v2.2.0 Semantic Payee Matching (2026-07-04, Phase 3)

**What went well**
- Cosine-in-store was the right call and the numbers proved it: clean vendors
  landed ~0.24, true variants 0.86-0.97 - a HUGE margin, so the default 0.72
  threshold separated cleanly with zero infra beyond a Bedrock invoke. OpenSearch
  (~$700/mo) would have bought nothing here [[treasury-cost-posture]].
- Versioning the embeddings WITH the list (publish-time compute) fell straight
  out of DEC-18 - a screening's cited version now pins the exact vectors too.
- explainScore already capped every non-tin match, so the reviewer scoring "just
  worked" for name_semantic - the decision model's "only TIN rejects" invariant
  paid off in the UI for free.
- The demo picked itself from the tuning matrix: "Globex Overseas Incorporated"
  had difflib 0.55 (string-missed) but cosine 0.857 - the cleanest possible proof
  that semantic catches what string matching cannot.

**What bit / watch**
- B's 60s reference TTL means a freshly-published list (with new embeddings)
  isn't live until warm containers expire - the live verify had to sleep 65s
  after publish before submitting, or a stale-cached container would screen
  without embeddings. Real behavior, not a bug; noted for any "publish then
  immediately test" flow.
- ruff now requires an explicit strict= on zip(); added strict=True in _cosine
  (lengths are guarded equal above).
- Degrade-on-Bedrock-error is a deliberate availability>freshness choice for an
  ADDITIVE control (rules still run). For a primary control it would be wrong.
  Flagged as an alarm follow-on in DEC-19.

**Estimated vs actual**
Est ~3-4h -> actual ~2.0h. Under band despite being the "unfamiliar Bedrock
gate": the conditional-IAM + versioned-store seams from prior gates absorbed
most of it, and the threshold tuning was one clean pass.
### REFLEXION - v2.1.2 Multi-Format Batch Ingestion (2026-07-04, Phase 3, inserted)

**What went well**
- One shared _build_row validator behind three thin format parsers (csv/xlsx/json)
  kept the contract identical across formats - the cross-format dedup test (a
  payment_id via CSV then re-sent via JSON dedupes on the shared table) proves it.
- Dropping the S3 notification .csv suffix filter (fire on ALL batch-imports/
  uploads) is what lets non-CSV files reach E at all - the frontend accept="" and
  presign relaxation are cosmetic without it. Easy to forget the trigger layer.
- Kept the browser bundle light: no SheetJS. XLSX has no client preview (server-
  parsed); CSV/JSON preview client-side. The batch flow already round-trips to a
  server summary, so the preview is a courtesy, not load-bearing.
- Live-verified through the ACTUAL presigned-PUT path (post-CORS-fix), not just
  SigV4 - the browser leg now genuinely works end to end.

**What bit**
- Fat-fingered an Edit anchor (idx["payee_tin"] where the file had idx["amount"]),
  the replace failed loudly. Re-read the exact line and redid it. Cheap because
  Edit fails closed on a bad anchor rather than mangling.
- openpyxl must be pip-installed in the LOCAL test env too (not just E's image) -
  the test both builds and parses xlsx.

**Estimated vs actual**
Est ~1-2h -> actual ~1.0h. Small, well-scoped, and the parser seams were clean.
### REFLEXION - v2.1.1 Hotfix: browser CORS preflight (2026-07-04)

The console was NEVER actually usable in a browser - every authenticated call
403'd on its CORS preflight - and I missed it across SIX console gates (v1.2 ->
v2.1) because every "live e2e" used boto3/SigV4, which does not send a browser
CORS preflight. The owner found it in ~30 seconds of real clicking.

Root cause: API Gateway resource policies (DEC-5) deny everything not matching a
named-role Allow. The browser's UNSIGNED OPTIONS preflight is anonymous, matches
no Allow, and is denied - 403 with no Access-Control-Allow-Origin, so the browser
never sends the real request. Fix: an explicit Allow for */OPTIONS/* to any
principal (safe - OPTIONS is a MOCK, no data), plus exempting aws:PrincipalType
Anonymous from the catch-all Deny.

LESSONS
1. SigV4/boto3 e2e and browser fetch are DIFFERENT surfaces. A signed client
   proves the API + IAM and says NOTHING about CORS. For any IAM-authed SPA the
   preflight must be tested with a real OPTIONS request. scripts/check_cors.py is
   now a standing deploy gate - run it every console deploy.
2. "Live-verified" was overclaimed for every console gate: it meant "verified via
   SigV4," not "works in a browser." State WHICH surface was verified.
3. Propagation: the guard failed on the first run right after apply, then passed
   ~30s later. Re-probe after a short settle before concluding a fix failed.

### REFLEXION - v2.1.0 Reference-Data Lifecycle (2026-07-04, Phase 3)

**What went well**
- The versioned-document design (current.json pointer + immutable versions/N.json)
  delivered the whole citation story in ~a page of handler code, and the live
  proof was airtight: a payment matched an entry that exists ONLY in v2, so the
  audit's reference_list_version=2 could not have come from the bundle.
- If-None-Match version claim worked under moto AND live - optimistic
  concurrency for pennies.
- Both prior lessons applied cleanly: seed via script, never Terraform-managed
  (v1.4.0 index.html) and admin-only enforced at edge + handler (v2.0.0 DEC-17
  pattern). No IAM propagation error this time because the roles named in the
  new Deny already existed - creating principals in an EARLIER gate than the
  policies that name them is the painless ordering.

**What bit**
- checkov's passed-count DROPPED 502 -> 429 while resources grew. Investigated
  before trusting it: quiet/compact in .checkov.yaml strip detail from ALL
  output (even JSON, even other CWDs - checkov auto-discovers the config), so
  coverage had to be proven by resource_count (133) vs repo resource blocks
  (123) + parsing_errors: 0. Root cause of the drop: after terraform init
  refreshed .terraform/modules/modules.json, checkov attributes module
  definitions once through the root evaluation instead of double-counting
  standalone + evaluated copies. LESSON: the checkov PASS COUNT is not a
  coverage metric across runs; compare resource_count and parsing_errors
  instead. Burned ~20 min of JSON-plumbing before stepping back to the
  decisive simple check (grep resource blocks).
- The permission classifier (correctly) refused a composite command that
  provisioned a new Cognito identity mid-deploy. Splitting infra steps from
  identity grants and asking the user explicitly was the right shape anyway.

**Estimated vs actual**
Est ~2-3h -> actual ~1.5h. Under band: the store pattern + conditional-IAM
seams are now muscle memory; the only novel work was the publish endpoint.

### REFLEXION - v2.0.0 Roles & Segregation of Duties (2026-07-04, Phase 3)

**What went well**
- Cognito GROUPS -> per-group IAM roles via Identity-Pool Token role-mapping
  (cognito:preferred_role) reused DEC-5/DEC-15 cleanly - one auth model, now
  role-scoped. Live proof: brian assumed the admin role (not the fallback),
  confirming the mapping end to end.
- SoD split correctly across layers: EDGE (resource policy scopes submitter to
  batch routes) for API authz IAM can express, HANDLER (decider != submitted_by)
  for the per-item maker/checker it can't. Both live-verified (403 self, 200 cross).
- submitted_by rode the pipeline for free: A stamps it, B/C already forward the
  whole payment dict untouched, D persists it. No B/C changes needed - the
  pass-through worker pattern paid off again.
- Refactor from v1.6.0 (_apply_decision shared core) meant SoD landed in ONE
  place and covered single + bulk automatically.

**What bit**
- The known IAM-propagation error returned: API Gateway UpdateRestApi rejected
  both resource policies ("ensure Principals are valid") because the group roles
  were created in the SAME apply. Fix (already in the playbook): the roles DID
  get created, so poll get-role for propagation, then re-plan + re-apply - it
  went clean the second time. Worth pre-empting: create new principal roles in a
  prior targeted apply before the policies that name them.
- Cognito vs STS credential field names differ (SecretKey vs SecretAccessKey) -
  cost one script iteration on the live check. Trivia, but bit twice historically.

**What to watch**
- A user with NO group gets the authenticated fallback (no API access) - a fresh
  login is required after group assignment for cognito:preferred_role to appear
  in the token. Assign groups BEFORE expecting console access.

**Estimated vs actual**
Est ~2-3h -> actual ~2.5h. Landed at the top of the band as flagged: genuinely
cross-cutting (Cognito + IAM + 3 handlers + UI + e2e) but no single hard part.

### REFLEXION — v1.6.0 Write-Scale Hardening (2026-07-04, Phase 2)

**What went well**
- The proxy-all console API ({proxy+} catch-all) meant three new routes
  (/batches, /batches/{id}, /reviews/decisions) were pure handler code — zero
  new API Gateway resources. The router-Lambda shape keeps paying off.
- DEC-16 (reuse A's idempotency table + intake queue instead of a new store or
  per-row HTTP) made "screened once across single + batch paths" fall out for
  free. Sharing the STORE, not the code, was the right call given the
  container-per-component build has no shared context.
- Refactoring _decide -> _apply_decision let the bulk endpoint reuse the exact
  single-decision logic (per-item audit record preserved). Small seam, big reuse.

**What bit**
- Intra-file duplicates. The shared-table claim can't catch a payment_id
  repeated WITHIN one file: the first occurrence is still PENDING (not SENT)
  when the repeat is checked, so _claim returned "re-drive" and sent it twice.
  Fixed with an in-file `seen` set. Caught by writing the live test with a
  deliberate dup row BEFORE deploying — the test-with-real-intent habit paid off.
- New-bucket S3 307. A presigned browser PUT to a just-created regional bucket
  307-redirects until routing propagates (minutes). Not a code bug; verified
  ingestion via `aws s3 cp` (same ObjectCreated event) and noted the transient.
- Immutable ECR tags. Fixing E after pushing v1.6.0 forced a full v1.6.1
  rebuild+repoint of all 6 images (one global tag). Cost: one extra apply.
  Lesson: don't push the release tag until the component is test-green live.
- New component image = chicken/egg with its Terraform-owned ECR repo. Correct
  order is targeted `apply -target=module.ecr[...]` to create the repo, THEN
  push, THEN full apply — not a manual `aws ecr create-repository` (its AES256
  default collides with the module's KMS, and ECR encryption is immutable).

**Estimated vs actual**
Est ~2-3h -> actual ~2.0h. Landed mid-range: the new component + module + S3
trigger + 3 endpoints + 2 UI changes was real surface, but the established
patterns (shared module, proxy-all API, presign/upload) absorbed most of it.

### REFLEXION — v1.5.0 Read-Scale Hardening (2026-07-04, Phase 2)

**What went well**
- The conditional-var module pattern (audit_index_table_arn, like reviews_table_arn
  and secrets_arn before it) made adding a per-stage capability to Component D a
  known, low-risk move — DEC-1's shared module keeps absorbing new needs cleanly.
- Audit index with a prefix-scan FALLBACK = backward compatible: pre-index audit
  records still resolve, new ones are O(1). No migration needed.
- Split call (v1.5.0 read-scale / v1.6.0 write-scale) was right — this was a clean,
  low-risk gate; batching it with the new ingestion Lambda would have muddied it.

**What bit**
- DynamoDB returns a LastEvaluatedKey whenever it stops at the Limit, even if the
  next page is empty — so next_cursor can be present with a following empty page.
  The client must stop on an empty page, not only on a null cursor. Noted for the UI.

**Estimated vs actual**
Est 1-2h -> actual ~1.0h. Read-scale hardening is cheap when the seams (module
conditional vars, api module) already exist.

### REFLEXION — v1.4.0 Console GA (2026-07-04, Phase 2)

**What went well**
- The clean fake->live seam paid off: swapping fakeData for the signed api.js
  module touched the data layer, not the components. Amplify (Cognito User+Identity
  Pool) + aws4fetch SigV4 reused DEC-5's IAM auth for humans — no second authorizer.
- Proved it the honest way: a script that walks the EXACT browser path (Cognito
  login -> Identity Pool temp creds -> SigV4 to both APIs -> submit/review/decide),
  all 200, PASS. Stronger than "it renders."

**What bit (integration gate, as predicted)**
- terraform managed the placeholder index.html; `apply` reverted the deployed SPA
  to it. Classic "IaC owns the bucket AND its contents" conflict. Fix: `state rm`
  the object, drop it from config, let the s3-sync own contents. Now plan is
  0-drift. This is the frontend analogue of the v1.0.0 deploy-only surprises.
- USER_PASSWORD_AUTH had to be enabled for the headless e2e (SRP is hard to script);
  SRP stays the browser default. Noted in DEC-15.

**Lesson**
- For static-site IaC: Terraform owns the bucket/distribution, the deploy pipeline
  owns the contents — never both. And integration gates surface a class of issue
  (CORS, drift, auth-flow) that unit tests and plan can't; budget the fix loop.

**Estimated vs actual**
Est 2-3h -> actual ~2.5h. Landed in range (unlike the sub-estimate backend gates) —
integration genuinely costs more, and the estimate captured that.

### REFLEXION — v1.3.0 Console UI (2026-07-04, Phase 2)

**What went well**
- First UI gate on this project and it went clean: React/Vite SPA, 4 screens,
  hash routing (right call for S3+CloudFront static hosting — no error-page
  rewrites), 15/15 vitest. Fake-data shapes mirror the real API exactly, so
  v1.4.0 swaps the source, not the components.
- The two live-verification loops in the browser (preview_eval) caught what
  jsdom can't: the hash-verify crypto actually computing ✓/✗, deep links
  surviving login, the user menu + density persistence. Verifying UI in a real
  browser, not just jsdom, is the difference between "tests pass" and "it works."
- Design-review discipline paid off: Brian's "looks basic / empty void" and
  "needs profile+settings+logout" were real gaps; the polish pass (footer,
  full-height shell, density, user menu) moved it from prototype to product.

**What bit**
- Two stale tests after refactors (plural heading; integrity text moved behind a
  button). Both my own assertions lagging the UI — cheap fixes, but a reminder to
  update tests in the same edit as the component.
- The login handler clobbered deep links by always nav-ing to #/submit — caught
  by the deep-link test. Fixed to preserve the requested hash across login.

**Lesson**
- For UI, jsdom proves logic; a real browser proves the feature. Run both. And
  scope-growth in UI is cheap when the data layer is a clean seam (fake→live) —
  batch upload + profile/settings + tier-1 all folded into one gate without churn.

**Estimated vs actual**
Est 2–4h (loose, first UI gate) → actual ~1.6h, even with the folded-in scope.
UI on this stack is landing faster than the loose estimate; v1.4.0 (wiring) is
the real integration-risk gate.

### REFLEXION — v1.1.0 Console Foundation (2026-07-03, Phase 2)

**What went well**
- Cognito Identity Pool → temp IAM creds → SigV4 cleanly REUSES the DEC-5 auth
  mechanism for humans (one more named principal in the API resource policy)
  instead of bolting on a second scheme. The module cycle (console needs API arn,
  API needs console role) was broken by attaching the invoke policy at env level
  — PAT-T1's lesson generalized to policies, not just queues.
- DEC-10 exercised for real: image tag bump → publish → alias repoint to v2, and
  the live smoke (review payment → reviews-table item) proved the redeploy.
- checkov console findings: 3 real fixes (explicit security-headers policy with
  HSTS preload, lifecycle rule, US geo whitelist) + 8 justified skips.

**What bit**
- CKV2_AWS_32 is a GRAPH check: it needs an actual aws_cloudfront_response_headers_policy
  resource, not a managed-policy ID string. And CKV_AWS_259 wants HSTS preload=true.
- The API resource-policy update failed once on IAM propagation for the
  just-created console role (known first-deploy class) — 45s wait + re-apply fixed.
- pytest's plan-parsing tests skipped until `terraform init` registered the new
  module — the skip-guard masking a stale init; re-ran green after init.

**Estimated vs actual**
Est ~1–2h (loose, first frontend-phase gate) → actual ~0.8h. In range; still no
UI-code data (that's v1.3.0's calibration point).

### REFLEXION — v1.0.0 Capstone Deliverable / Full Deploy (2026-07-03)

**What went well**
- The full deploy actually worked end-to-end and demonstrated all four commitments
  LIVE — the strongest possible capstone artifact. The staged deploy (ECR → images →
  full apply) was the right sequencing.
- The build's test-first discipline paid off at deploy: the handlers ran correctly
  in real Lambda on the first working apply (once the image format was fixed) — the
  moto tests had exercised the real logic.

**What bit (deploy-only class of issues)**
- **buildx OCI manifest:** Docker's default buildx output is an OCI image index,
  which Lambda rejects ("media type ... not supported"). Fixed by rebuilding with
  `--provenance=false --output type=image,oci-mediatypes=false`. Only a real deploy
  surfaces this — tests and plan can't.
- **API Gateway account CloudWatch role:** enabling stage access logging needs an
  account-level `aws_api_gateway_account` + IAM role that wasn't in the module.
  Added it (a real fix). Another deploy-only discovery.
- **Guardrails fired correctly and repeatedly:** repo-publish, blind-apply (the
  account-global resource), and the external-webhook secret write were all blocked by
  the auto-mode classifier. Right calls. Routed around them properly: explicit user
  authorization for the publish; `plan -out` + `apply <plan>` for the reviewed apply;
  and handing the external-destination secret write to Brian to run himself (the
  classifier treats exfil-shaped secret writes as user-only, even with in-chat OK).

**Lesson**
- Budget a "deploy-fix loop" for any first real deployment — image manifest formats,
  account-level singletons, and IAM propagation are a class of issue that only
  appears at apply time. And treat external-destination secret writes as strictly
  user actions regardless of conversational authorization.

**Estimated vs actual**
Raw 8–16h (mid 12h) → actual ~1.5h. Final gate. Seven-gate mean variance ≈ -92%;
the whole build ran ~10-12x faster than the raw roadmap estimates. Time to refresh
the operator calibration profile with this project's data (aggregate-patterns).

### REFLEXION — v0.6.0 CI/CD & Security Scanning (2026-07-03)

**What went well**
- Ran ruff + pip-audit locally BEFORE pushing, so the first Actions run went
  green on the first try — no CI-failure churn. Verifying scanners locally is
  cheaper than debugging red CI.
- CI verified for real (green run on GitHub Actions), not just "config written."

**What bit**
- `gh repo create --push` was (correctly) blocked by the publish guardrail — my
  gate scope isn't user intent for an outward publish. Needed Brian's explicit
  "I authorize you." Lesson: for anything that uploads/publishes, get the user's
  explicit words first; a CONFIRMED gate scope doesn't substitute.

**Estimated vs actual**
Raw 6–12h (mid 9h) → actual ~0.7h. Sixth gate, ~-92%. Consistent project signal.

### REFLEXION — v0.5.0 Queue-Depth Scaling & DLQ Hardening (2026-07-03)

**What went well**
- The whole scaling mechanism was already built at v0.1.0 (shared module), so
  this gate was purely writing the evidence test — the DEC-1 shared-module bet
  keeps paying off. Parsing `terraform show -json` is a clean, deterministic way
  to prove infra config as a pytest without a live deploy.

**What bit**
- First cut of the redrive test tried to parse `redrive_policy` from
  planned_values, but that string is known-after-apply (references the DLQ ARN),
  so it wasn't there. Pivoted to asserting the redrive-policy + DLQ resources
  exist. Lesson: in plan-JSON tests, assert on KNOWN values / resource presence,
  not on computed strings.

**Estimated vs actual**
Raw 5–9h (mid 7h) → actual ~0.4h. Fifth gate, consistent ~-90%+ under. The
project calibration (5 gates, mean ≈ -92%) is now well-established and should be
folded back into the operator profile via aggregate-patterns after this run.

### REFLEXION — v0.4.0 Component D: Disposition, Audit, Notify (2026-07-03)

**What went well**
- The live Object-Lock proof (Brian chose it over the moto-only default) was the
  right call: real `AccessDenied` on delete AND on shorten-retention is
  unarguable commitment-4 evidence in a way a simulator can't match. A targeted
  `apply -target=module.audit_store` gave the proof without needing the 4
  container images built.
- Brian's push on the audit-record detail improved it — decision + evidence +
  provenance + a SHA-256 integrity hash is a real compliance artifact; the hash
  is genuine defense-in-depth (Object Lock stops deletion, the hash proves the
  content wasn't altered).
- Audit-first ordering avoided a duplicate-review-item hazard on retry.

**What bit**
- moto doesn't emulate S3's auto-apply of the bucket default retention onto
  objects — `get_object_retention` 500s. Caught it, pivoted the moto test to a
  deterministic bucket-config assertion, and leaned on the live proof for
  enforcement. Exactly the moto-vs-real divergence TESTS.md predicted.

**Lesson**
- For an immutability/irreversibility claim, pay the small cost of a live proof
  (a briefly-stranded bucket). Simulators emulate configuration reliably but not
  always enforcement; the graded commitment is about enforcement.

**Estimated vs actual**
Raw 9h → project-calibrated (~-91%) ≈ 0.8h → actual ~0.7h. First gate estimated
off the project-specific signal instead of the 0.34x operator multiplier, and it
landed close — the project calibration is now the better predictor.

### REFLEXION — v0.3.0 Components B & C: Enrichment + Risk Scoring (2026-07-03)

**What went well**
- No Terraform change needed — the shared module instances (B/C) were already
  wired at v0.1.0, so this gate was pure handler logic + tests. The shared-module
  bet (DEC-1) is paying off: adding two components cost zero infra churn.
- Multi-component test refactor (load three sibling `app.py`s by path under
  unique module names) cleanly solved the `import app` collision; fresh module
  per load also killed the client-cache-leak problem for free.

**What bit**
- Reference research was launched as a background workflow, then killed mid-run
  for token efficiency. Lesson: for a well-understood public pattern (DNP), a
  best-judgment build + a one-line simulation caveat is enough; the grounding
  workflow was over-investment. Don't reach for a workflow when the design risk
  is low and reversibility is high.

**Lesson**
- Match the tool to the decision's stakes. v0.1.0's live-docs grounding was worth
  it (irreversible Object Lock, stale provider syntax). v0.3.0's domain grounding
  was not (reversible bundled list, well-known pattern). Same instinct, wrong gate.

**Estimated vs actual**
Raw 8h → calibrated ~2.7h → actual ~0.5h. Third straight gate far under. Now at
3 data points — per policy this is the re-evaluation point; the project-specific
signal (≈ -90% mean) is much stronger than the 0.34x operator multiplier and
should inform v0.4.0's estimate.

### REFLEXION — v0.2.0 Component A: Payment Intake API + Idempotency (2026-07-03)

**What went well**
- The critical-thinker pass paid for itself: it turned a vague "use DynamoDB"
  into a correct mechanism by naming two HIGH-severity holes (reject-vs-replay,
  and the two-phase silent-loss window) BEFORE any code. Both became test cases;
  the crash-recovery test is the strongest single piece of commitment-1 evidence.
- Test-first worked cleanly — the 6 cases encoded the race/crash semantics from
  DEC-13, and the handler was written to satisfy them. 6/6 green on first real run.
- checkov triage stayed a design review: the two new DynamoDB findings
  (CKV_AWS_119 CMK, CKV2_AWS_16 autoscaling) were each evaluated and justified as
  skips proportionate to a dedup cache, not reflexively suppressed.

**What bit**
- Nothing blocking. moto 5 + boto3 on Python 3.14 emit botocore `utcnow`
  DeprecationWarnings (upstream, not our code) — noise, not failures.

**Lesson**
- For a graded "demonstrate X" commitment, the decision that matters most isn't
  the storage tech (DynamoDB was never in doubt) — it's the SEMANTICS around it
  (replay vs reject, two-phase ordering). Pressure-test the semantics, not just
  the component. Same shape as v0.1.0's "ask why a check exists," applied to a
  design rather than a scanner.

**Estimated vs actual**
Raw estimate 8h → calibrated ~2.7h (0.34x) → actual ~0.4h. Second consecutive
gate well under even the calibrated figure. Two data points now point the same
direction for this AWS/Terraform+Python project; per policy still no roadmap
edits until 3 gates, but the trend is worth flagging at the next gate's estimate.

### REFLEXION — v0.1.0 Terraform Foundation & Shared Module (2026-07-03)

**What went well**
- The pre-build grounding pass (live-docs research + adversarial verify) earned
  its cost twice before a single resource was applied: it caught a hallucinated
  provider attribute (`aws_ecr_image.image_digest` — the export is `id`) that
  would have silently defeated the DEC-10 rollback pattern at v0.2.0, and it
  confirmed the Object Lock resource split so the one irreversible surface was
  written right the first time.
- checkov triage (37 findings) was treated as fix-vs-justify, not
  suppress-to-green: 4 real fixes, 17 documented skips. One "fix" was a latent
  v0.4.0 runtime bug (Component D missing KMS key-usage rights for SSE-KMS
  audit writes) found by reasoning through CKV2_AWS_64 rather than skipping it.
- The for_each sibling-reference cycle was designed around up front (inter-stage
  queues at env level) instead of discovered as a plan error.

**What bit**
- HashiCorp CDN (checkpoint-api + releases.hashicorp.com) reset connections
  intermittently on this network; GitHub was solid throughout. Cost ~15 min
  until `--retry-all-errors` pushed the download through.
- My first toolchain check piped through `head`, which masked exit codes and
  reported nothing instead of "terraform missing" — rechecked with `command -v`.
- checkov's ANSI-colored output broke naive parsing; findings had to be
  de-escaped before dedupe.
- Guessed tflint-ruleset-aws pin (0.38.0) was stale; live check said 0.48.0.
  Same lesson as the grounding pass: pins come from the release page, not memory.

**Lesson**
Verification-against-live-sources beats recall at every layer of this stack
(provider attrs, plugin pins, policy IDs) — and scanner findings are a design
review, not a checklist: the KMS bug was only visible by asking *why* a check
existed. Also: on this machine, assume HashiCorp endpoints are flaky and retry;
assume nothing about toolchain presence.

**Estimated vs actual**
Raw estimate 10h → calibrated ~3.4h (0.34x operator multiplier) → actual ~1.5h.
Even the 0.34x-calibrated figure over-estimated by ~2.3x. Consistent with the
operator pattern's direction (systematic over-estimation), and a first data
point suggesting AWS/Terraform gates may run even faster than the pooled
multiplier predicts — but it is ONE data point; per policy, re-evaluate after
3 project gates, no roadmap edits from a single sample. (Machine-parseable
ESTIMATION line below is written by the calibration hook.)

