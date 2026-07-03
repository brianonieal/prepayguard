# MEMORY_CORRECTIONS.md — PrePayGuard ("Treasury")
# Calibration data and reflexion entries. Newest first within each section.

## REFLEXION LOG

ESTIMATION: gate=v0.1.0 estimated=10h actual=1.50h variance=-85% source=timelog errors_open=0 errors_close=0 date=2026-07-03T18:27:21Z

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

