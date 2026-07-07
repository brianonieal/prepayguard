# modules/scheduled_feeder - Component F: automated real-data feed (v3.3.0, DEC-23).
# An EventBridge schedule invokes a Lambda that pulls real awards from the public,
# keyless USAspending API and writes ONE JSON file to the batch-imports bucket. That
# reuses Component E's existing S3 trigger (DEC-16) to screen every row - no new
# screening path, no console upload. The feeder holds NO secret (public source) and
# only writes to the batch bucket's feed prefix.

locals {
  function_name = "${var.name_prefix}-feeder"
}

# ---------------------------------------------------------------------------
# IAM - least privilege: write feed files to the batch bucket + logs + xray ONLY.
# No idempotency table, no queue, no Bedrock, no secret (Component E does the
# claim/enqueue; the source is keyless public data).
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

resource "aws_iam_role" "feeder" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

data "aws_iam_policy_document" "feeder" {
  statement {
    sid       = "WriteLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.feeder.arn}:*"]
  }

  statement {
    sid       = "WriteFeedFile"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${var.batch_bucket_arn}/batch-imports/*"]
  }

  statement {
    sid       = "ReadFeedConfig"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.reference_bucket_arn}/reference/feeder-config/*"]
  }

  statement {
    sid       = "XRayTracing"
    effect    = "Allow"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "feeder" {
  name   = "${local.function_name}-policy"
  role   = aws_iam_role.feeder.id
  policy = data.aws_iam_policy_document.feeder.json
}

# ---------------------------------------------------------------------------
# Lambda - container image, versioned + aliased (DEC-2, DEC-10)
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "feeder" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "feeder" {
  function_name = local.function_name
  role          = aws_iam_role.feeder.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = ["x86_64"]
  memory_size   = var.memory_size
  timeout       = var.timeout
  publish       = true

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      BATCH_BUCKET         = var.batch_bucket_name
      FEED_LIMIT           = tostring(var.feed_limit)
      DEMO_POSITIVE_NAME   = var.demo_positive_name
      FEEDER_CONFIG_BUCKET = var.reference_bucket_name
    }
  }

  depends_on = [aws_cloudwatch_log_group.feeder, aws_iam_role_policy.feeder]
}

resource "aws_lambda_alias" "live" {
  name             = "live"
  description      = "Rollback pointer (DEC-10): repoint to a prior version to roll back."
  function_name    = aws_lambda_function.feeder.function_name
  function_version = aws_lambda_function.feeder.version
}

# ---------------------------------------------------------------------------
# EventBridge Scheduler -> feeder 'live' alias. Uses a timezone-aware schedule
# (DEC-23 amendment) so "business hours Eastern" tracks the EST/EDT DST shift
# automatically, which a UTC-only classic rule cannot. `enabled=false` is the
# stop switch. The scheduler assumes a dedicated role to invoke the feeder.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.function_name}-scheduler-role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "InvokeFeeder"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_alias.live.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${local.function_name}-scheduler-policy"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "feed" {
  name       = "${local.function_name}-schedule"
  group_name = "default"
  state      = var.enabled ? "ENABLED" : "DISABLED"

  # Business hours Eastern, all 7 days: fire at the top of each hour 9am to 5pm
  # in America/New_York (auto-adjusts EST/EDT). DEC-23 amendment.
  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.schedule_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_alias.live.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}
