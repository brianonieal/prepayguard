# MEMORY_CORRECTIONS.md — PrePayGuard ("Treasury")
# Calibration data and reflexion entries. Newest first within each section.

## REFLEXION LOG

ESTIMATION: gate=v0.3.0 estimated=8h actual=0.50h variance=-94% source=timelog errors_open=0 errors_close=0 date=2026-07-03T19:51:26Z
ESTIMATION: gate=v0.2.0 estimated=8h actual=0.40h variance=-95% source=timelog errors_open=0 errors_close=0 date=2026-07-03T19:18:04Z
ESTIMATION: gate=v0.1.0 estimated=10h actual=1.50h variance=-85% source=timelog errors_open=0 errors_close=0 date=2026-07-03T18:27:21Z

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

