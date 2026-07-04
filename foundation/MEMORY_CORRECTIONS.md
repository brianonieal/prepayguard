# MEMORY_CORRECTIONS.md — PrePayGuard ("Treasury")
# Calibration data and reflexion entries. Newest first within each section.

## REFLEXION LOG

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

