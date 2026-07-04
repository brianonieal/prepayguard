# environments/dev — instantiates every module and wires the pipeline:
#
#   caller (SigV4, payment-submitter role only)
#     └─> API Gateway ──> Lambda A (intake, idempotency)
#            └─> intake-out queue ──> Lambda B (enrichment)
#                   └─> enrichment-out queue ──> Lambda C (risk scoring)
#                          └─> risk-scoring-out queue ──> Lambda D (disposition)
#                                 ├─> audit bucket (S3 Object Lock, COMPLIANCE)
#                                 ├─> review queue (ambiguous → human)
#                                 └─> webhook notification (URL from Secrets Manager)
#
# Inter-stage queues B→C and C→D are created HERE, not inside the shared
# module: instances of one for_each module cannot reference sibling instances'
# outputs (self-referential for_each = cycle). A→B lives in api_intake_stage
# and D→review in review_queue — both single-instance modules, safe to
# reference from the for_each map.

data "aws_caller_identity" "current" {}

locals {
  name_prefix = "${var.project_name}-${var.environment}" # treasury-dev

  # One ECR repo per component image (DEC-2) + the console API router (v1.2.0)
  # + the batch-ingest worker (Component E, v1.6.0).
  components = ["intake", "enrichment", "risk_scoring", "disposition", "console_api", "batch_ingest"]

  # Lambda timeouts, defined once so queue visibility timeouts can be computed
  # from their CONSUMER's timeout (AWS guidance: visibility >= 6x timeout).
  stage_timeouts = {
    enrichment   = 60
    risk_scoring = 60
    disposition  = 60
  }
}

# ---------------------------------------------------------------------------
# Container registries (4x shared module — DEC-1/DEC-2)
# ---------------------------------------------------------------------------

module "ecr" {
  source   = "../../modules/ecr_repo"
  for_each = toset(local.components)

  repo_name    = "${local.name_prefix}-${replace(each.key, "_", "-")}"
  force_delete = true # dev only: allow teardown with images present
}

# ---------------------------------------------------------------------------
# Audit store (DEC-4, commitment 4) and human-review path (commitment 2)
# ---------------------------------------------------------------------------

module "audit_store" {
  source = "../../modules/audit_store"

  # Account ID suffix for global uniqueness.
  bucket_name    = "${local.name_prefix}-audit-${data.aws_caller_identity.current.account_id}"
  retention_days = var.audit_retention_days
}

module "review_queue" {
  source = "../../modules/review_queue"

  name_prefix = local.name_prefix
}

# ---------------------------------------------------------------------------
# DEC-7: webhook secret SHELL. The secret VALUE is set out-of-band at v0.4.0
# (aws secretsmanager put-secret-value) — never in Terraform state, tfvars,
# or git. Component D's role gets GetSecretValue on exactly this ARN.
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "review_webhook" {
  name        = "${local.name_prefix}/review-webhook-url"
  description = "Webhook URL Component D posts to when routing a payment to human review (DEC-7)."

  # Dev: immediate deletion on destroy so iterate/recreate never collides with
  # a name held in recovery. Production posture would keep the 30-day window.
  recovery_window_in_days = 0
}

# ---------------------------------------------------------------------------
# DEC-5: the ONE role allowed to invoke the Payment Intake API. The API's
# resource policy denies every other principal; this identity policy is the
# matching allow side. Test clients (v0.2.0 SigV4 tests) assume this role.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "submitter_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
}

resource "aws_iam_role" "payment_submitter" {
  name               = "${local.name_prefix}-payment-submitter"
  description        = "Sole principal permitted to call the Payment Intake API (DEC-5)."
  assume_role_policy = data.aws_iam_policy_document.submitter_assume.json
}

data "aws_iam_policy_document" "submitter_invoke" {
  statement {
    sid       = "InvokePaymentIntakeApi"
    effect    = "Allow"
    actions   = ["execute-api:Invoke"]
    resources = ["${module.api_intake.api_execution_arn}/*"]
  }
}

resource "aws_iam_role_policy" "submitter_invoke" {
  name   = "${local.name_prefix}-payment-submitter-invoke"
  role   = aws_iam_role.payment_submitter.id
  policy = data.aws_iam_policy_document.submitter_invoke.json
}

# ---------------------------------------------------------------------------
# Component A — Payment Intake API
# ---------------------------------------------------------------------------

module "console" {
  source = "../../modules/console_foundation"

  name_prefix      = local.name_prefix
  site_bucket_name = "${local.name_prefix}-console-${data.aws_caller_identity.current.account_id}"
}

# Console users' invoke policy lives HERE (not in the console module) to break
# the console<->api_intake reference cycle.
data "aws_iam_policy_document" "console_invoke" {
  statement {
    sid     = "InvokeConsoleFacingApis"
    effect  = "Allow"
    actions = ["execute-api:Invoke"]
    resources = [
      "${module.api_intake.api_execution_arn}/*",
      "${module.console_api.api_execution_arn}/*",
    ]
  }
}

# Console read/action API (v1.2.0)
module "console_api" {
  source = "../../modules/console_api"

  name_prefix              = local.name_prefix
  image_uri                = "${module.ecr["console_api"].repository_url}:${var.placeholder_image_tag}"
  allowed_invoker_role_arn = module.console.authenticated_role_arn
  reviews_table_name       = module.console.reviews_table_name
  reviews_table_arn        = module.console.reviews_table_arn
  reviews_status_index_arn = module.console.reviews_status_index_arn
  audit_index_table_name   = module.console.audit_index_table_name
  audit_index_table_arn    = module.console.audit_index_table_arn
  audit_bucket_name        = module.audit_store.bucket_name
  audit_bucket_arn         = module.audit_store.bucket_arn
  audit_kms_key_arn        = module.audit_store.kms_key_arn
  console_origin           = module.console.console_url
  uploads_bucket_name      = "${local.name_prefix}-console-uploads-${data.aws_caller_identity.current.account_id}"
  # v1.6.0 batch ingestion: console_api presigns the CSV upload + polls the summary.
  batch_bucket_name  = module.batch_ingest.batch_bucket_name
  batch_bucket_arn   = module.batch_ingest.batch_bucket_arn
  batches_table_name = module.batch_ingest.batches_table_name
  batches_table_arn  = module.batch_ingest.batches_table_arn
  stage              = var.environment
}

# ---------------------------------------------------------------------------
# Component E — Batch Ingest (v1.6.0, write-scale). S3-triggered; reuses
# Component A's idempotency store + intake queue (DEC-16) so single-API and
# batch submissions dedupe against each other.
# ---------------------------------------------------------------------------

module "batch_ingest" {
  source = "../../modules/batch_ingest_stage"

  name_prefix            = local.name_prefix
  image_uri              = "${module.ecr["batch_ingest"].repository_url}:${var.placeholder_image_tag}"
  batch_bucket_name      = "${local.name_prefix}-batch-imports-${data.aws_caller_identity.current.account_id}"
  idempotency_table_name = module.api_intake.idempotency_table_name
  idempotency_table_arn  = module.api_intake.idempotency_table_arn
  intake_queue_url       = module.api_intake.output_queue_url
  intake_queue_arn       = module.api_intake.output_queue_arn
  console_origin         = module.console.console_url
}

resource "aws_iam_role_policy" "console_invoke" {
  name   = "${local.name_prefix}-console-invoke"
  role   = module.console.authenticated_role_name
  policy = data.aws_iam_policy_document.console_invoke.json
}

module "api_intake" {
  source = "../../modules/api_intake_stage"

  name_prefix = local.name_prefix
  image_uri   = "${module.ecr["intake"].repository_url}:${var.placeholder_image_tag}"
  allowed_invoker_role_arns = [
    aws_iam_role.payment_submitter.arn,
    module.console.authenticated_role_arn, # Treasury Console users (v1.1.0)
  ]
  stage = var.environment

  console_origin = module.console.console_url

  # A→B queue visibility must cover its consumer (B, enrichment).
  output_queue_visibility_timeout = 6 * local.stage_timeouts.enrichment

  env_vars = {
    STAGE = "intake"
    # OUTPUT_QUEUE_URL intentionally deferred: the queue is created inside the
    # module; the handler reads it at v0.2.0 via this module's own wiring.
  }
}

# ---------------------------------------------------------------------------
# Inter-stage queues created at environment level (cycle-free for_each inputs)
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "enrichment_out" {
  name                       = "${local.name_prefix}-enrichment-out"
  message_retention_seconds  = 345600 # 4 days
  visibility_timeout_seconds = 6 * local.stage_timeouts.risk_scoring
  sqs_managed_sse_enabled    = true
}

resource "aws_sqs_queue" "risk_scoring_out" {
  name                       = "${local.name_prefix}-risk-scoring-out"
  message_retention_seconds  = 345600
  visibility_timeout_seconds = 6 * local.stage_timeouts.disposition
  sqs_managed_sse_enabled    = true
}

# ---------------------------------------------------------------------------
# Components B, C, D — the shared queue_worker_stage, 3x via for_each (DEC-1)
# ---------------------------------------------------------------------------

locals {
  stages = {
    enrichment = {
      input_queue_arn       = module.api_intake.output_queue_arn
      input_queue_url       = module.api_intake.output_queue_url
      output_queue_arn      = aws_sqs_queue.enrichment_out.arn
      memory_size           = 512
      timeout               = local.stage_timeouts.enrichment
      max_concurrency       = 10
      secrets_arn           = null
      audit_bucket_arn      = null
      audit_kms_key_arn     = null
      reviews_table_arn     = null
      audit_index_table_arn = null
      env_vars = {
        STAGE            = "enrichment"
        OUTPUT_QUEUE_URL = aws_sqs_queue.enrichment_out.url
      }
    }

    risk_scoring = {
      input_queue_arn       = aws_sqs_queue.enrichment_out.arn
      input_queue_url       = aws_sqs_queue.enrichment_out.url
      output_queue_arn      = aws_sqs_queue.risk_scoring_out.arn
      memory_size           = 512
      timeout               = local.stage_timeouts.risk_scoring
      max_concurrency       = 10
      secrets_arn           = null
      audit_bucket_arn      = null
      audit_kms_key_arn     = null
      reviews_table_arn     = null
      audit_index_table_arn = null
      env_vars = {
        STAGE            = "risk_scoring"
        OUTPUT_QUEUE_URL = aws_sqs_queue.risk_scoring_out.url
      }
    }

    disposition = {
      input_queue_arn  = aws_sqs_queue.risk_scoring_out.arn
      input_queue_url  = aws_sqs_queue.risk_scoring_out.url
      output_queue_arn = module.review_queue.queue_arn
      memory_size      = 512
      timeout          = local.stage_timeouts.disposition
      max_concurrency  = 10
      # DEC-7: the ONLY stage holding a secret — scoped to this one ARN.
      secrets_arn = aws_secretsmanager_secret.review_webhook.arn
      # Commitment 4: the ONLY stage that writes the audit log (+ its CMK).
      audit_bucket_arn  = module.audit_store.bucket_arn
      audit_kms_key_arn = module.audit_store.kms_key_arn
      # Console v1.1.0/v1.5.0: D writes the reviews table + the audit index.
      reviews_table_arn     = module.console.reviews_table_arn
      audit_index_table_arn = module.console.audit_index_table_arn
      env_vars = {
        STAGE              = "disposition"
        REVIEW_QUEUE_URL   = module.review_queue.queue_url
        AUDIT_BUCKET_NAME  = module.audit_store.bucket_name
        WEBHOOK_SECRET_ARN = aws_secretsmanager_secret.review_webhook.arn
        REVIEWS_TABLE_NAME = module.console.reviews_table_name
        AUDIT_INDEX_TABLE  = module.console.audit_index_table_name
      }
    }
  }
}

module "worker" {
  source   = "../../modules/queue_worker_stage"
  for_each = local.stages

  name_prefix           = local.name_prefix
  stage_name            = each.key
  image_uri             = "${module.ecr[each.key].repository_url}:${var.placeholder_image_tag}"
  input_queue_arn       = each.value.input_queue_arn
  input_queue_url       = each.value.input_queue_url
  output_queue_arn      = each.value.output_queue_arn
  memory_size           = each.value.memory_size
  timeout               = each.value.timeout
  max_concurrency       = each.value.max_concurrency
  env_vars              = each.value.env_vars
  secrets_arn           = each.value.secrets_arn
  audit_bucket_arn      = each.value.audit_bucket_arn
  audit_kms_key_arn     = each.value.audit_kms_key_arn
  reviews_table_arn     = each.value.reviews_table_arn
  audit_index_table_arn = each.value.audit_index_table_arn
}
