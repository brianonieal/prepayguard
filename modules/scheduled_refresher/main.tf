# modules/scheduled_refresher - Component G: automated reference-list refresh
# (v3.4.0, DEC-24). EventBridge Scheduler invokes a Lambda daily; it re-pulls the
# real SAM.gov exclusions (keyless OpenSanctions mirror), re-embeds them (Titan),
# and republishes the versioned reference document (DEC-18) ONLY when the list
# changed. Least-privilege: read/write the reference bucket + invoke the one embed
# model + logs/xray. No secret (public source), no queue.

locals {
  function_name = "${var.name_prefix}-refresher"
}

# ---- Lambda execution IAM ---------------------------------------------------

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

resource "aws_iam_role" "refresher" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

data "aws_iam_policy_document" "refresher" {
  statement {
    sid       = "WriteLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.refresher.arn}:*"]
  }

  statement {
    sid       = "ReadWriteReference"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${var.reference_bucket_arn}/reference/*"]
  }

  statement {
    sid       = "EmbedEntries"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel"]
    resources = [var.embed_model_arn]
  }

  statement {
    sid       = "XRayTracing"
    effect    = "Allow"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "refresher" {
  name   = "${local.function_name}-policy"
  role   = aws_iam_role.refresher.id
  policy = data.aws_iam_policy_document.refresher.json
}

# ---- Lambda (container image, versioned + aliased: DEC-2, DEC-10) ------------

resource "aws_cloudwatch_log_group" "refresher" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "refresher" {
  function_name = local.function_name
  role          = aws_iam_role.refresher.arn
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
      REFERENCE_BUCKET = var.reference_bucket_name
      REFRESH_LIMIT    = tostring(var.refresh_limit)
      EMBED_MODEL      = var.embed_model
    }
  }

  depends_on = [aws_cloudwatch_log_group.refresher, aws_iam_role_policy.refresher]
}

resource "aws_lambda_alias" "live" {
  name             = "live"
  description      = "Rollback pointer (DEC-10): repoint to a prior version to roll back."
  function_name    = aws_lambda_function.refresher.function_name
  function_version = aws_lambda_function.refresher.version
}

# ---- EventBridge Scheduler -> refresher 'live' alias (timezone-aware) --------

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
    sid       = "InvokeRefresher"
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

resource "aws_scheduler_schedule" "refresh" {
  name       = "${local.function_name}-schedule"
  group_name = "default"
  state      = var.enabled ? "ENABLED" : "DISABLED"

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
