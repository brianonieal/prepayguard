# BOOTSTRAP.md: standing PrePayGuard up on a fresh AWS account

This is the missing-until-now setup runbook: how another engineer takes an empty AWS
account and this repository to a running, live system. It complements `README.md`
(what the system is), `ARCHITECTURE.md` (how it is shaped), and `docs/ROLLBACK.md`
(how to undo a deploy). Every command is account-agnostic: the scripts resolve the
account, region, bucket, distribution, and repositories from `terraform output`, so
you do not edit any hardcoded ids.

The reference deployment runs in `us-east-2`. Nothing here is account-specific except
your own credentials and the model-access enablement in step 1.

## 0. Prerequisites

- An AWS account and credentials with permission to create the resources in
  `environments/dev/` (Lambda, SQS, S3, DynamoDB, API Gateway, Cognito, CloudFront,
  KMS, Secrets Manager, EventBridge Scheduler, ECR, IAM). Export them the usual way
  (`aws configure`, `AWS_PROFILE`, or env vars). Confirm with `aws sts get-caller-identity`.
- Docker running (the eight Lambda handlers are container images).
- Node 20+ and npm (for the console SPA build).
- Terraform 1.15.x and tflint. The repo expects project-local binaries under
  `.tools/bin` (gitignored); add them to PATH: `export PATH="$PWD/.tools/bin:$PATH"`.
- Python 3.12 with `boto3` (for the seed/ingest/verify scripts).

## 1. Enable Bedrock model access (one-time, per account/region)

Components B and G and the console briefs call Bedrock. In the AWS console, go to
**Bedrock, Model access** in `us-east-2` and enable:

- `amazon.titan-embed-text-v2:0` (semantic-match and reference embeddings)
- `amazon.nova-lite-v1:0` (reviewer adjudication briefs)

Without this, B/G invocations and the console brief return AccessDenied. This is an
account action AWS gates, so it cannot be done in Terraform.

## 2. Create the ECR repositories first

Images must exist before the Lambdas that reference them can be created, so create the
registries before the first full apply:

```sh
cd environments/dev
terraform init
terraform apply -target='module.ecr'
cd ../..
```

## 3. Build and push all eight images

```sh
scripts/build-push-images.sh
```

This resolves the repo URLs and tag (`placeholder_image_tag` in
`environments/dev/terraform.tfvars`) from Terraform, logs in to ECR, and builds and
pushes every component with the Docker v2 media type Lambda requires. See the header
of that script for the immutable-tag rule (bump the tag, rebuild all, re-apply).

## 4. Apply the full stack

```sh
terraform -chdir=environments/dev apply
```

This creates every component, queue, table, bucket (including the Object Lock audit
bucket), the Cognito pools, API Gateways, CloudFront, and the two EventBridge
schedules. `terraform apply` is always a manual, deliberate action (DEC-6; CI is
plan-only). Note the outputs; you will not need to copy them by hand, the scripts read
them back.

Warning: the audit bucket uses S3 Object Lock COMPLIANCE. Read the irreversibility
block in `terraform.tfvars` before setting `audit_retention_days` to anything other
than the dev default of 1 day. Retention cannot be shortened on a written object by
anyone, ever (DEC-4).

## 5. Set the one runtime secret (out-of-band)

The review-notification webhook URL lives only in Secrets Manager, never in Terraform
state or git (DEC-7). Set its value after the apply created the secret shell:

```sh
aws secretsmanager put-secret-value \
  --secret-id "$(terraform -chdir=environments/dev output -raw webhook_secret_arn)" \
  --secret-string 'https://your-webhook-endpoint.example/notify'
```

If you have no webhook, any reachable URL works for a demo; the review path also has an
age-of-oldest-message alarm backstop that does not depend on it.

## 6. Seed the screening reference list

Publish version 1 of the Do Not Pay list (synthetic bundled data), then optionally pull
the real SAM.gov exclusions:

```sh
python scripts/seed_reference_data.py
python scripts/ingest_sam_exclusions.py --source opensanctions   # optional: real SAM (keyless mirror)
```

Component G will keep the list current on its daily schedule after this.

## 7. Provision console users

There is no public sign-up (operator-provisioned only, by design). Create a user and
put them in a role group (`submitter`, `reviewer`, `admin`, or `auditor`, mapped to IAM
roles by Cognito):

```sh
POOL=$(terraform -chdir=environments/dev output -json console_cognito | python -c 'import sys,json;print(json.load(sys.stdin)["user_pool_id"])')
aws cognito-idp admin-create-user --user-pool-id "$POOL" --username you@example.gov
aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL" --username you@example.gov --group-name admin
```

## 8. Deploy the console SPA

```sh
scripts/deploy-console.sh
```

This regenerates `console/src/config.js` from Terraform outputs, builds the SPA, syncs
it to the site bucket, and invalidates CloudFront, all resolved from `terraform output`
(no hardcoded bucket or domain). It prints the live URL when done.

## 9. Verify end to end

```sh
python scripts/check_cors.py            # OPTIONS preflight on every route (browser CORS)
python scripts/console_e2e.py           # full Cognito -> SigV4 -> API path
python scripts/live_object_lock_proof.py  # proves a written audit object cannot be deleted or shortened
python scripts/send_payment.py          # submit one payment through the intake API
```

Captured runs of these against the reference account are in `docs/evidence/`.

## 10. Operate and roll back

- **Roll back a bad deploy:** repoint the Lambda `live` alias to the prior version
  (seconds, no rebuild). Full procedure and the reference-data and infra rollback tiers
  are in `docs/ROLLBACK.md`.
- **Stop the schedules:** set `feeder_enabled=false` / `refresher_enabled=false` in
  `terraform.tfvars` and re-apply.
- **Tear down (non-audit):** `terraform destroy` removes everything except the Object
  Lock audit bucket, which cannot be deleted while retention holds (DEC-4, by design);
  destroy it only after its retention window has elapsed.

## Known gaps a successor should be aware of

- Terraform state is local (`environments/dev/backend.tf`); safe for one operator, not
  for a team. Move to remote state (S3 + DynamoDB lock) and set the `AWS_PLAN_ROLE_ARN`
  secret so `plan.yml` reflects real drift before a second operator applies.
- CloudWatch alarms are configured but have no notification target wired yet; see the
  risk-rating table in `docs/HANDOFF.md` section 4.
