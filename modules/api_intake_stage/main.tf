# modules/api_intake_stage — Component A: Payment Intake API.
# REST API Gateway (not HTTP API v2) because DEC-5 requires a RESOURCE POLICY
# scoping invoke to one IAM role, and resource policies exist only on REST
# APIs. Method auth is AWS_IAM (SigV4). The Lambda performs the payment-ID
# idempotency check (commitment 1 — handler logic lands at v0.2.0; the
# idempotency backing store is a v0.2.0 decision recorded in ARCHITECTURE.md)
# and forwards accepted payments to the output SQS queue consumed by
# Component B.
#
# DLQ note (deliberate deviation from the original scaffold comment): this
# module creates NO DLQ. A's Lambda is invoked synchronously by API Gateway —
# async DLQs don't apply; errors return to the caller as HTTP responses. The
# DLQ for A's OUTPUT queue belongs to its consumer (Component B's
# queue_worker_stage instance), per the consumer-owns-failure-handling pattern.

locals {
  function_name = "${var.name_prefix}-intake"
}

# ---------------------------------------------------------------------------
# Output queue: A → B. Created here (A is a single-instance module, so B's
# for_each map can reference it without self-reference cycles).
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "output" {
  name                       = "${local.function_name}-out"
  message_retention_seconds  = 345600 # 4 days
  visibility_timeout_seconds = var.output_queue_visibility_timeout
  sqs_managed_sse_enabled    = true
}

# ---------------------------------------------------------------------------
# IAM — execution role scoped to logs + send-to-output + X-Ray
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

resource "aws_iam_role" "intake" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

data "aws_iam_policy_document" "intake" {
  statement {
    sid    = "WriteLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.intake.arn}:*"]
  }

  statement {
    sid       = "SendToOutputQueue"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.output.arn]
  }

  statement {
    sid    = "XRayTracing"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "intake" {
  name   = "${local.function_name}-policy"
  role   = aws_iam_role.intake.id
  policy = data.aws_iam_policy_document.intake.json
}

# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "intake" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/apigw/${local.function_name}-access"
  retention_in_days = var.log_retention_days
}

# ---------------------------------------------------------------------------
# Lambda — container image, versioned + aliased (DEC-2, DEC-10)
# ---------------------------------------------------------------------------

resource "aws_lambda_function" "intake" {
  function_name = local.function_name
  role          = aws_iam_role.intake.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = ["x86_64"]
  memory_size   = var.memory_size
  timeout       = var.timeout
  publish       = true

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
    aws_cloudwatch_log_group.intake,
    aws_iam_role_policy.intake,
  ]
}

resource "aws_lambda_alias" "live" {
  name             = "live"
  description      = "Stable pointer for rollback: repoint to prior version to roll back (DEC-10)"
  function_name    = aws_lambda_function.intake.function_name
  function_version = aws_lambda_function.intake.version
}

# ---------------------------------------------------------------------------
# API Gateway — REST API, AWS_IAM auth (DEC-5), Lambda proxy integration
# ---------------------------------------------------------------------------

resource "aws_api_gateway_rest_api" "intake" {
  name        = "${local.function_name}-api"
  description = "Payment Intake API (Component A). AWS_IAM auth per DEC-5."

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  # Replacement (if ever forced) stands up the new API before tearing down the
  # old one — no intake blackout window (CKV_AWS_237).
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_resource" "payments" {
  rest_api_id = aws_api_gateway_rest_api.intake.id
  parent_id   = aws_api_gateway_rest_api.intake.root_resource_id
  path_part   = "payments"
}

resource "aws_api_gateway_method" "post_payments" {
  rest_api_id   = aws_api_gateway_rest_api.intake.id
  resource_id   = aws_api_gateway_resource.payments.id
  http_method   = "POST"
  authorization = "AWS_IAM" # DEC-5: SigV4-verified caller identity, not a static header
}

resource "aws_api_gateway_integration" "lambda" {
  rest_api_id             = aws_api_gateway_rest_api.intake.id
  resource_id             = aws_api_gateway_resource.payments.id
  http_method             = aws_api_gateway_method.post_payments.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_alias.live.invoke_arn # via alias: DEC-10 rollback covers the API path
}

# DEC-5 resource policy: invoke is scoped to ONE named IAM role.
#   - Allow: exactly the payment-submitter role (no wildcard principals —
#     CKV_AWS_283).
#   - Deny: everyone whose aws:PrincipalArn is not that role, as belt-and-
#     braces against any other same-account principal carrying its own
#     execute-api identity permissions.
# aws:PrincipalArn resolves to the ROLE ARN (not the session ARN) for
# assumed-role callers, so matching the role ARN is exact.
data "aws_iam_policy_document" "api_resource_policy" {
  statement {
    sid    = "AllowSubmitterRoleInvoke"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = [var.allowed_invoker_role_arn]
    }

    actions   = ["execute-api:Invoke"]
    resources = ["${aws_api_gateway_rest_api.intake.execution_arn}/*"]
  }

  statement {
    sid    = "DenyAllButSubmitterRole"
    effect = "Deny"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions   = ["execute-api:Invoke"]
    resources = ["${aws_api_gateway_rest_api.intake.execution_arn}/*"]

    condition {
      test     = "StringNotEquals"
      variable = "aws:PrincipalArn"
      values   = [var.allowed_invoker_role_arn]
    }
  }
}

resource "aws_api_gateway_rest_api_policy" "intake" {
  rest_api_id = aws_api_gateway_rest_api.intake.id
  policy      = data.aws_iam_policy_document.api_resource_policy.json
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.intake.function_name
  qualifier     = aws_lambda_alias.live.name
  principal     = "apigateway.amazonaws.com"
  # IAM resource wildcards span path segments: covers every stage/method/path
  # of THIS API only.
  source_arn = "${aws_api_gateway_rest_api.intake.execution_arn}/*"
}

resource "aws_api_gateway_deployment" "intake" {
  rest_api_id = aws_api_gateway_rest_api.intake.id

  # Redeploy exactly when the API surface actually changes.
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.payments.id,
      aws_api_gateway_method.post_payments.id,
      aws_api_gateway_integration.lambda.id,
      data.aws_iam_policy_document.api_resource_policy.json,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.lambda,
    aws_api_gateway_rest_api_policy.intake,
  ]
}

resource "aws_api_gateway_stage" "this" {
  rest_api_id          = aws_api_gateway_rest_api.intake.id
  deployment_id        = aws_api_gateway_deployment.intake.id
  stage_name           = var.stage
  xray_tracing_enabled = true

  # Access logs: who called, with what identity, and what came back — the
  # intake edge of an audit-minded pipeline logs its callers.
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      requestTime      = "$context.requestTime"
      httpMethod       = "$context.httpMethod"
      resourcePath     = "$context.resourcePath"
      status           = "$context.status"
      responseLength   = "$context.responseLength"
      callerIdentity   = "$context.identity.caller"
      callerAccount    = "$context.identity.accountId"
      userArn          = "$context.identity.userArn"
      sourceIp         = "$context.identity.sourceIp"
      integrationError = "$context.integration.error"
    })
  }
}
