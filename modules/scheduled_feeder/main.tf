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
      BATCH_BUCKET       = var.batch_bucket_name
      FEED_LIMIT         = tostring(var.feed_limit)
      DEMO_POSITIVE_NAME = var.demo_positive_name
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
# EventBridge schedule -> feeder 'live' alias. `enabled=false` is the stop switch.
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "${local.function_name}-schedule"
  description         = "Automated real-data feed (DEC-23): pull USAspending awards into the screening pipeline."
  schedule_expression = var.schedule_expression
  state               = var.enabled ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "feeder" {
  rule      = aws_cloudwatch_event_rule.schedule.name
  target_id = "feeder"
  arn       = aws_lambda_alias.live.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.feeder.function_name
  qualifier     = aws_lambda_alias.live.name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}
