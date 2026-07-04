# modules/queue_worker_stage — SHARED MODULE (DEC-1)
# Used 3x via for_each for Components B (enrichment), C (risk_scoring),
# D (disposition). One shape: SQS-triggered Lambda container image with DLQ,
# redrive, scaling config (commitment 3), queue-depth + DLQ alarms
# (commitments 2/3), and a least-privilege IAM role. Per-stage differences are
# confined to variables (image, env vars, sizing) plus two conditional IAM
# statements (secrets for DEC-7, audit-bucket write for commitment 4) that only
# Component D sets.

locals {
  function_name = "${var.name_prefix}-${var.stage_name}"
  # Queue NAME derived from ARN (arn:aws:sqs:region:account:name → index 5).
  input_queue_name = element(split(":", var.input_queue_arn), 5)
}

# ---------------------------------------------------------------------------
# Dead-letter queue (commitment 2: failure routing)
# Owned by the CONSUMING stage: this module attaches a redrive policy to its
# input queue (created upstream) pointing at this DLQ. 14-day retention gives
# maximum time to inspect failed payments before loss.
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "dlq" {
  name                      = "${local.function_name}-dlq"
  message_retention_seconds = 1209600 # 14 days (SQS maximum)
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue_redrive_policy" "input" {
  queue_url = var.input_queue_url
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

# Only the declared input queue may use this DLQ as its dead-letter target.
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.url
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [var.input_queue_arn]
  })
}

# ---------------------------------------------------------------------------
# IAM — least privilege, scoped to exactly the resources this stage touches
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "worker" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

data "aws_iam_policy_document" "worker" {
  statement {
    sid    = "WriteLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    # Scoped to this function's log group only (not logs:* on *).
    resources = ["${aws_cloudwatch_log_group.worker.arn}:*"]
  }

  statement {
    sid    = "ConsumeInputQueue"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [var.input_queue_arn]
  }

  statement {
    sid       = "SendToOutputQueue"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [var.output_queue_arn]
  }

  statement {
    sid    = "XRayTracing"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
    ]
    # X-Ray trace ingestion does not support resource-level scoping.
    resources = ["*"]
  }

  # DEC-7: added ONLY when secrets_arn is non-null (Component D's instance).
  # Scoped to that single secret ARN — this is the demonstrated least-privilege
  # secret retrieval for course objectives 7 and 9.
  dynamic "statement" {
    for_each = var.secrets_arn == null ? [] : [var.secrets_arn]
    content {
      sid       = "ReadReviewWebhookSecret"
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [statement.value]
    }
  }

  # Commitment 4: added ONLY when audit_bucket_arn is non-null (Component D).
  # PutObject inherits the bucket's Object Lock default retention; no delete or
  # retention-modification permissions are granted to anyone.
  dynamic "statement" {
    for_each = var.audit_bucket_arn == null ? [] : [var.audit_bucket_arn]
    content {
      sid       = "WriteAuditRecords"
      effect    = "Allow"
      actions   = ["s3:PutObject"]
      resources = ["${statement.value}/*"]
    }
  }

  # Console (v1.1.0): added ONLY when reviews_table_arn is non-null (Component D).
  # Writes the queryable review item the dashboard lists.
  dynamic "statement" {
    for_each = var.reviews_table_arn == null ? [] : [var.reviews_table_arn]
    content {
      sid       = "WriteReviewItems"
      effect    = "Allow"
      actions   = ["dynamodb:PutItem"]
      resources = [statement.value]
    }
  }

  # Companion to WriteAuditRecords: the audit bucket is SSE-KMS with a CMK, so
  # the WRITER principal needs key usage rights or PutObject fails at runtime
  # (caught during the v0.1.0 checkov triage, before it could bite at v0.4.0).
  # Scoped to the one audit key; GenerateDataKey covers writes, Decrypt covers
  # multipart/bucket-key session derivation.
  dynamic "statement" {
    for_each = var.audit_kms_key_arn == null ? [] : [var.audit_kms_key_arn]
    content {
      sid    = "UseAuditKmsKey"
      effect = "Allow"
      actions = [
        "kms:GenerateDataKey",
        "kms:Decrypt",
      ]
      resources = [statement.value]
    }
  }
}

resource "aws_iam_role_policy" "worker" {
  name   = "${local.function_name}-policy"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker.json
}

# ---------------------------------------------------------------------------
# Logs — explicit group so retention is controlled and IAM stays scoped
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

# ---------------------------------------------------------------------------
# Lambda — container image (DEC-2), versioned for alias rollback (DEC-10)
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "worker" {
  function_name = local.function_name
  role          = aws_iam_role.worker.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = ["x86_64"] # uniform across all four components; declared to avoid image/function platform mismatch at invoke
  memory_size   = var.memory_size
  timeout       = var.timeout

  # DEC-10: publish a numbered version on each deploy; the "live" alias points
  # at it. Rollback = repoint the alias to the prior version.
  publish = true

  tracing_config {
    mode = "Active"
  }

  dynamic "environment" {
    for_each = length(var.env_vars) > 0 ? [1] : []
    content {
      variables = var.env_vars
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.worker,
    aws_iam_role_policy.worker,
  ]
}

resource "aws_lambda_alias" "live" {
  name             = "live"
  description      = "Stable pointer for rollback: repoint to prior version to roll back (DEC-10)"
  function_name    = aws_lambda_function.worker.function_name
  function_version = aws_lambda_function.worker.version
}

# ---------------------------------------------------------------------------
# Event source mapping — SQS → Lambda (commitment 3: queue-depth scaling)
# maximum_concurrency caps how many concurrent Lambda instances this queue can
# drive (min 2 per AWS). Partial-batch failure reporting keeps one bad payment
# from poisoning a whole batch (commitment 2 hygiene).
# ---------------------------------------------------------------------------

resource "aws_lambda_event_source_mapping" "input" {
  event_source_arn                   = var.input_queue_arn
  function_name                      = aws_lambda_alias.live.arn # via alias, so DEC-10 rollback applies to the trigger too
  batch_size                         = var.batch_size
  maximum_batching_window_in_seconds = var.maximum_batching_window_in_seconds
  function_response_types            = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = var.max_concurrency
  }
}

# ---------------------------------------------------------------------------
# Alarms
# ---------------------------------------------------------------------------

# Commitment 3 signal: input queue depth. Fires when the backlog grows faster
# than the (capped) worker fleet drains it.
resource "aws_cloudwatch_metric_alarm" "queue_depth" {
  alarm_name          = "${local.function_name}-queue-depth"
  alarm_description   = "Input queue depth high for ${var.stage_name} (scaling pressure signal, commitment 3)"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Average"
  period              = 60
  evaluation_periods  = var.alarm_evaluation_periods
  threshold           = var.queue_depth_alarm_threshold
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = local.input_queue_name
  }
}

# Commitment 2 signal: anything in the DLQ is a failed payment awaiting manual
# attention. Threshold 1 — a compliance pipeline has no acceptable DLQ noise.
resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${local.function_name}-dlq-not-empty"
  alarm_description   = "Messages present in ${var.stage_name} DLQ (component-failure routing, commitment 2)"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }
}
