# SPEC.md
# Current-gate detail. Updated each gate.

## LAST CLOSED: v0.6.0 — CI/CD & Security Scanning
**Status:** CLOSED (tagged). CI **green on GitHub Actions** —
`github.com/brianonieal/prepayguard` (private). DEC-6/8/9/10 satisfied.
- `ci.yml`: fmt/validate/tflint + pytest 29/29 + ruff + pip-audit + checkov ✓
- `plan.yml`: plan-on-PR, no auto-apply (awaits `AWS_PLAN_ROLE_ARN` secret)
- rollback runbook (`docs/ROLLBACK.md`, DEC-10)

## NEXT GATE: v1.0.0 — Capstone Handoff Package (DEC-11)
Six sections: architecture notes (forward-looking), tests (rendered report),
deployment docs, security findings (narrative + risk-rating table + raw scan
appendix), residual risks, follow-on work. Assembled from ARCHITECTURE.md,
TESTS.md, CHANGELOG, scan output, and the live proof evidence. Opens on **GO**.

## PENDING (not gated)
Full deploy — 4 container images built+pushed to ECR + full `terraform apply` —
for a live end-to-end run + Grype image scan. Only `audit_store` is live today.
Worth deciding whether to slot before v1.0.0 so the handoff shows a real run.

## DECISIONS SNAPSHOT
14 of 14 LOCKED. No open questions.
