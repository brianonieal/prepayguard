# queue_worker_stage

The shared worker-stage module (DEC-1). Instantiated three times via `for_each`
— Components B (enrichment), C (risk_scoring), and D (disposition) — so DLQ,
redrive, scaling, and alarm configuration cannot drift between stages of a
compliance-relevant pipeline.

## What one instance creates

| Resource | Purpose |
|---|---|
| `aws_lambda_function` (container image, `publish = true`) | The worker (DEC-2). Versioned for alias rollback (DEC-10). |
| `aws_lambda_alias` `live` | Rollback pointer; the event source mapping binds to it. |
| `aws_lambda_event_source_mapping` + `scaling_config` | SQS trigger; `maximum_concurrency` is the commitment-3 scaling lever. |
| `aws_sqs_queue` (DLQ) + redrive policy on the input queue | Commitment 2: failures land somewhere inspectable. |
| `aws_sqs_queue_redrive_allow_policy` | Only the declared input queue may target this DLQ. |
| `aws_iam_role` + scoped policy | Least privilege: consume input, send output, write own logs, X-Ray. |
| `aws_cloudwatch_log_group` | Explicit retention; keeps the IAM logs statement scoped. |
| Two `aws_cloudwatch_metric_alarm` | Input-queue depth (commitment 3) and DLQ-not-empty (commitment 2). |

## Queue ownership (why input queues are variables, not resources)

Instances of a `for_each` module cannot reference each other's outputs (the
`for_each` map would reference the module itself — a cycle). So inter-stage
queues are created **outside** this module (by `api_intake_stage` for A→B, by
the environment for B→C and C→D, by `review_queue` for D's output) and passed
in by ARN + URL. This module owns everything about **consuming** its input
queue: the DLQ, the redrive policy attachment, the depth alarm, and the event
source mapping.

## Deviations from the original scaffold comment (documented, deliberate)

- **`input_queue_url` added** — `aws_sqs_queue_redrive_policy` addresses queues
  by URL; deriving URLs from ARNs is construction-by-convention and brittle.
- **`audit_bucket_arn` added (null default)** — Component D must write audit
  records (commitment 4). Same conditional-statement pattern DEC-1 already
  approved for `secrets_arn`; only D's instance sets either. This is the
  "watch for divergence" case DEC-1's risk note anticipated, handled without
  forking the module.
- **`name_prefix` + tuning knobs added** (batch size, batching window,
  max receive count, alarm threshold/periods, log retention) — sensible
  defaults, overridable per stage without editing the module.

## Conditional IAM (DEC-7 / commitment 4)

`secrets_arn` non-null ⇒ one extra statement: `secretsmanager:GetSecretValue`
on exactly that ARN. `audit_bucket_arn` non-null ⇒ one extra statement:
`s3:PutObject` on `<bucket>/*` (writes inherit the bucket's Object Lock
Compliance retention; nothing grants delete or retention modification).
Both default null ⇒ B and C carry zero secret/bucket permissions.
