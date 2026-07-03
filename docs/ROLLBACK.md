# Rollback Runbook (DEC-10)

One mechanism, identical across all four components: **Lambda versions + aliases.**

## How it works
- Every deploy publishes a numbered Lambda **version** (`publish = true`).
- A **`live` alias** points at exactly one version. API Gateway (Component A) and
  every SQS event source mapping (B/C/D) invoke the **alias**, never `$LATEST`.
- **Rollback = repoint the alias to the prior version.** Traffic follows the
  alias immediately; no rebuild, no redeploy, no infrastructure churn.

## Procedure
1. Identify the last-good version:
   ```
   aws lambda list-versions-by-function --function-name treasury-dev-<component> \
     --query 'Versions[].Version'
   ```
2. Repoint the alias:
   ```
   aws lambda update-alias --function-name treasury-dev-<component> \
     --name live --function-version <PRIOR_VERSION>
   ```
   Or in Terraform: set the alias's `function_version` to the prior number and apply.
3. Verify: `aws lambda get-alias --function-name treasury-dev-<component> --name live`.

## Scope
- **Code rollback** (a bad handler image): alias repoint, seconds.
- **Infrastructure rollback** (a bad Terraform change): `git` — every gate is
  tagged `syntaris-gate-vX.Y.Z`; `terraform plan` against a checked-out tag shows
  the exact reversion diff before any apply.

## Not used
Full `terraform destroy`/re-apply as rollback was rejected (DEC-10) — too coarse
and slow. Note the audit bucket (S3 Object Lock COMPLIANCE) cannot be rolled back
or destroyed until retention expires, by design (DEC-4) — that is the one
deliberately irreversible surface.
