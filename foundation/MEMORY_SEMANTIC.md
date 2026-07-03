# MEMORY_SEMANTIC.md — PrePayGuard ("Treasury")
# Durable patterns learned IN THIS PROJECT (AWS / Terraform / Python stack).
# Cross-project pre-fills from other stacks (Supabase, Vercel, Render, etc.)
# are explicitly excluded per the project brief, section 4.

## PAT-T1: for_each module instances cannot reference siblings
A `for_each` module call whose map values reference outputs of the same module
call is a self-reference error. Consequence for pipelines: inter-stage queues
are created OUTSIDE the shared worker module (env level, or in single-instance
modules like api_intake_stage) and passed in as ARN+URL variables. The consumer
module still owns DLQ, redrive attachment (aws_sqs_queue_redrive_policy), depth
alarm, and event source mapping for its input queue.

## PAT-T2: KMS key policies trip checkov's IAM-document triad
CKV_AWS_109 / CKV_AWS_111 / CKV_AWS_356 fire on any key policy's canonical
root statement (`kms:*`, resource `"*"`). In a KEY policy, `"*"` legally means
"this key" and the root statement prevents key orphaning. Resolution: inline
`# checkov:skip` comments with justification on the policy document — never a
global skip (the checks are valid for identity policies).

## PAT-T3: SSE-KMS buckets require key-usage rights on WRITERS
Adding CMK encryption to a bucket silently adds an IAM requirement to every
principal that writes: kms:GenerateDataKey (+ kms:Decrypt for multipart /
bucket-key sessions). Missing grants fail at RUNTIME, not plan/apply. Whenever
a CMK lands on a bucket, walk every writer's role in the same change.

## PAT-T4: aws_ecr_image exports the digest as `id`
There is no `image_digest` export on the aws_ecr_image data source (it exists
only as an optional INPUT). Digest-pin with
`${repository_url}@${data.aws_ecr_image.x.id}` and prefer `code_sha256` as the
container-image update trigger on aws_lambda_function (provider-preferred for
Image packages, feeds publish=true → alias rollback per DEC-10).

## PAT-T5: HashiCorp endpoints are flaky on this network; GitHub is not
checkpoint-api.hashicorp.com and releases.hashicorp.com intermittently reset
TLS connections (both curl and PowerShell stacks; IPv4 and IPv6 both affected,
both eventually succeed). Always download with
`curl --retry 8 --retry-delay 2 --retry-all-errors`; expect `terraform init`
provider pulls to need retries some days. GitHub API/releases were reliable.

## PAT-T6: project-local toolchain on Windows without admin
`.tools/bin/` (gitignored) + direct release-zip downloads works for
terraform/tflint with zero elevation; checkov via `pip install --user` and
invoked as `python -m checkov.main` (user Scripts dir not on PATH). Export
PATH per-invocation in Bash: `export PATH="/d/PrePayGuard/.tools/bin:$PATH"`.

## PAT-T7: shell checks that pipe to head/tail mask exit codes
`tool version | head -1 || echo missing` never fires the `||` (head exits 0).
Presence checks use `command -v tool` — this exact bug cost a re-check this
project. Related: checkov output carries ANSI codes; strip with
`sed 's/\x1b\[[0-9;]*m//g'` before parsing.
