# modules/console_api — the Treasury Console's read/action API (v1.2.0).
# One router Lambda (container image, versioned + aliased per DEC-10) behind an
# IAM-authed REST API whose resource policy admits ONLY the console
# authenticated role (same DEC-5 mechanism as the intake API).
# CORS: browsers preflight cross-origin SigV4 calls, so OPTIONS is un-authed
# MOCK returning CORS headers; data responses carry the headers from the handler.

locals {
  function_name = "${var.name_prefix}-console-api"
  # v2.1.0: role groupings for the resource policy; ADMIN_ROLE_NAME lets the
  # handler distinguish admin from reviewer (both may invoke most routes).
  reviewer_admin_role_arns = [var.reviewer_role_arn, var.admin_role_arn]
  all_named_role_arns      = [var.reviewer_role_arn, var.admin_role_arn, var.submitter_role_arn, var.auditor_role_arn]
  admin_role_name          = element(split("/", var.admin_role_arn), 1)
  auditor_role_name        = element(split("/", var.auditor_role_arn), 1)
}

# ---------------------------------------------------------------------------
# IAM — scoped to exactly what the three routes touch
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

resource "aws_iam_role" "api" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

data "aws_iam_policy_document" "api" {
  statement {
    sid       = "WriteLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }

  statement {
    sid       = "ReviewsTableReadWrite"
    effect    = "Allow"
    actions   = ["dynamodb:Scan", "dynamodb:Query", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:BatchWriteItem", "dynamodb:DescribeTable"] # BatchWriteItem/DescribeTable: v3.1.0 demo reset
    resources = [var.reviews_table_arn, var.reviews_status_index_arn]                                                                               # v1.5.0: Query the GSI
  }

  # v1.5.0: O(1) audit lookup via the payment_id -> key index.
  # v2.4.0: Scan for analytics + the auditor audit-log. v3.1.0: BatchWriteItem for reset.
  statement {
    sid       = "AuditIndexRead"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:Scan", "dynamodb:BatchWriteItem", "dynamodb:DescribeTable"]
    resources = [var.audit_index_table_arn]
  }

  statement {
    sid       = "AuditRecords"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${var.audit_bucket_arn}/*"]
  }

  statement {
    sid       = "AuditPrefixSearch"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.audit_bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["audit/*"]
    }
  }

  # PAT-T3: SSE-KMS bucket — readers need Decrypt, writers GenerateDataKey.
  statement {
    sid       = "UseAuditKmsKey"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.audit_kms_key_arn]
  }

  # Case-document uploads (v1.4.0): presign PUT + list/get. DeleteObject (v3.2.1):
  # the admin demo reset clears uploaded case documents.
  statement {
    sid       = "CaseUploads"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket", "s3:DeleteObject"]
    resources = [aws_s3_bucket.uploads.arn, "${aws_s3_bucket.uploads.arn}/*"]
  }

  # v2.1.0 reference-data lifecycle: read the current list + history, publish
  # new versions (handler enforces admin-only; the edge denies reviewer writes).
  statement {
    sid       = "ReferenceStoreReadWrite"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${var.reference_bucket_arn}/reference/*"]
  }

  statement {
    sid       = "ReferenceStoreListVersions"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.reference_bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["reference/*"]
    }
  }

  # v2.2.0 embeddings (publish) + v2.3.0 briefs (Converse). Scoped to exactly the
  # two foundation models this API uses, nothing else in Bedrock.
  statement {
    sid       = "InvokeBedrockModels"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel"]
    resources = [var.embed_model_arn, var.brief_model_arn]
  }

  # v1.6.0 batch ingestion: presign the CSV upload (PutObject) and poll the
  # batch summary Component E writes (GetItem/Scan). Enqueue + dedup stay on E.
  # v3.2.1: ListBucket + DeleteObject so the admin demo reset clears batch uploads.
  statement {
    sid       = "BatchUploads"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:ListBucket", "s3:DeleteObject"]
    resources = [var.batch_bucket_arn, "${var.batch_bucket_arn}/*"]
  }

  statement {
    sid       = "BatchSummaryRead"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:Scan", "dynamodb:BatchWriteItem", "dynamodb:DescribeTable"] # BatchWriteItem/DescribeTable: v3.1.0 demo reset
    resources = [var.batches_table_arn]
  }

  # v3.1.0 demo reset: clear the intake idempotency table (Component A's dedup
  # store) so the same sample payment_ids can be re-submitted after a reset.
  # Handler enforces admin-only + a typed confirmation.
  statement {
    sid       = "IdempotencyReset"
    effect    = "Allow"
    actions   = ["dynamodb:Scan", "dynamodb:BatchWriteItem", "dynamodb:DescribeTable"]
    resources = [var.idempotency_table_arn]
  }

  # v3.5.0: on-demand feed runs. The config object lives under reference/ and is
  # already covered by ReferenceStoreReadWrite; this only adds invoking the feeder.
  statement {
    sid       = "InvokeFeederOnDemand"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [var.feeder_alias_arn]
  }

  statement {
    sid       = "XRayTracing"
    effect    = "Allow"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "${local.function_name}-policy"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

# ---------------------------------------------------------------------------
# Lambda
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/apigw/${local.function_name}-access"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  function_name = local.function_name
  role          = aws_iam_role.api.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = ["x86_64"]
  memory_size   = 256
  timeout       = 29
  publish       = true

  tracing_config {
    mode = "Active"
  }

  environment {
    variables = {
      REVIEWS_TABLE_NAME  = var.reviews_table_name
      AUDIT_BUCKET_NAME   = var.audit_bucket_name
      AUDIT_INDEX_TABLE   = var.audit_index_table_name
      UPLOADS_BUCKET_NAME = aws_s3_bucket.uploads.id
      BATCH_BUCKET        = var.batch_bucket_name
      BATCHES_TABLE       = var.batches_table_name
      IDEMPOTENCY_TABLE   = var.idempotency_table_name
      REFERENCE_BUCKET    = var.reference_bucket_name
      ADMIN_ROLE_NAME     = local.admin_role_name
      AUDITOR_ROLE_NAME   = local.auditor_role_name
      EMBED_MODEL         = var.embed_model
      BRIEF_MODEL         = var.brief_model
      FEEDER_FUNCTION_ARN = var.feeder_alias_arn
      CONSOLE_ORIGIN      = var.console_origin
    }
  }

  depends_on = [aws_cloudwatch_log_group.api, aws_iam_role_policy.api]
}

resource "aws_lambda_alias" "live" {
  name             = "live"
  description      = "Rollback pointer (DEC-10)"
  function_name    = aws_lambda_function.api.function_name
  function_version = aws_lambda_function.api.version
}

# ---------------------------------------------------------------------------
# REST API — proxy-all to the router, IAM auth, console-role-only policy
# ---------------------------------------------------------------------------

resource "aws_api_gateway_rest_api" "console" {
  name        = local.function_name
  description = "Treasury Console read/action API (console authenticated role only)."

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.console.id
  parent_id   = aws_api_gateway_rest_api.console.root_resource_id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_method" "proxy_any" {
  rest_api_id   = aws_api_gateway_rest_api.console.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "ANY"
  authorization = "AWS_IAM"

  request_parameters = {
    "method.request.path.proxy" = true
  }
}

resource "aws_api_gateway_integration" "proxy_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.console.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy_any.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_alias.live.invoke_arn
}

# CORS preflight: browsers cannot SigV4-sign OPTIONS, so it is un-authed MOCK
# returning only CORS headers (no data path).
resource "aws_api_gateway_method" "proxy_options" {
  rest_api_id   = aws_api_gateway_rest_api.console.id
  resource_id   = aws_api_gateway_resource.proxy.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "proxy_options" {
  rest_api_id = aws_api_gateway_rest_api.console.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.proxy_options.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = jsonencode({ statusCode = 200 })
  }
}

resource "aws_api_gateway_method_response" "proxy_options" {
  rest_api_id = aws_api_gateway_rest_api.console.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.proxy_options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = true
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
  }
}

resource "aws_api_gateway_integration_response" "proxy_options" {
  rest_api_id = aws_api_gateway_rest_api.console.id
  resource_id = aws_api_gateway_resource.proxy.id
  http_method = aws_api_gateway_method.proxy_options.http_method
  status_code = aws_api_gateway_method_response.proxy_options.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = "'${var.console_origin}'"
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization,X-Amz-Date,X-Amz-Security-Token'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,PUT,OPTIONS'"
  }

  depends_on = [aws_api_gateway_integration.proxy_options]
}

data "aws_iam_policy_document" "resource_policy" {
  # CORS preflight: the browser sends an UNSIGNED (anonymous) OPTIONS before every
  # SigV4 call. Without an explicit allow it 403s with no CORS headers and the
  # whole browser surface fails. OPTIONS is a MOCK returning only CORS headers
  # (no Lambda, no data), so allowing it to any principal is safe + standard. The
  # DenyAllButNamedRoles below already exempts the anonymous type.
  statement {
    sid    = "AllowCorsPreflight"
    effect = "Allow"
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    actions   = ["execute-api:Invoke"]
    resources = ["${aws_api_gateway_rest_api.console.execution_arn}/*/OPTIONS/*"]
  }

  # Reviewers + admins: the whole API (reviewer reference-writes carved out below).
  statement {
    sid    = "AllowReviewerAdminAllPaths"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = local.reviewer_admin_role_arns
    }
    actions   = ["execute-api:Invoke"]
    resources = ["${aws_api_gateway_rest_api.console.execution_arn}/*"]
  }

  # v2.4.0: the read-only auditor is admitted on GET routes only (analytics, audit
  # log, cases, evidence) - method-scoped so it can never decide, publish, or submit.
  statement {
    sid    = "AllowAuditorReadOnly"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [var.auditor_role_arn]
    }
    actions   = ["execute-api:Invoke"]
    resources = ["${aws_api_gateway_rest_api.console.execution_arn}/*/GET/*"]
  }

  # v2.1.0: publishing a new screening list is admin-only. Edge-deny the reviewer
  # role on the write route (defense in depth with the handler's admin check).
  statement {
    sid    = "DenyReviewerReferenceWrites"
    effect = "Deny"
    principals {
      type        = "AWS"
      identifiers = [var.reviewer_role_arn]
    }
    actions   = ["execute-api:Invoke"]
    resources = ["${aws_api_gateway_rest_api.console.execution_arn}/*/PUT/reference"]
  }

  # v3.2.1: the demo reset is admin-only in the handler; deny it to the reviewer at
  # the edge too (defense in depth for a destructive route, mirroring the reference
  # write deny) so a reviewer principal can never even reach the reset Lambda.
  statement {
    sid    = "DenyReviewerReset"
    effect = "Deny"
    principals {
      type        = "AWS"
      identifiers = [var.reviewer_role_arn]
    }
    actions   = ["execute-api:Invoke"]
    resources = ["${aws_api_gateway_rest_api.console.execution_arn}/*/POST/admin/reset"]
  }

  # v3.5.0: in-console feed control is admin-only (handler enforces _is_admin).
  # Edge-deny every non-admin named role on the feed routes (defense in depth); the
  # Deny overrides the auditor's GET-only allow for GET /feed/config too.
  statement {
    sid    = "DenyNonAdminFeedControl"
    effect = "Deny"
    principals {
      type        = "AWS"
      identifiers = [var.reviewer_role_arn, var.auditor_role_arn, var.submitter_role_arn]
    }
    actions   = ["execute-api:Invoke"]
    resources = ["${aws_api_gateway_rest_api.console.execution_arn}/*/*/feed/*"]
  }

  # Submitters: ONLY the batch-upload routes (upload a CSV + poll its summary).
  # Scoped at the edge so a submitter can never reach /reviews/decisions even if
  # an identity policy were mis-scoped (defense in depth for the maker/checker split).
  statement {
    sid    = "AllowSubmitterBatchPaths"
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [var.submitter_role_arn]
    }
    actions = ["execute-api:Invoke"]
    resources = [
      "${aws_api_gateway_rest_api.console.execution_arn}/*/POST/batches",
      "${aws_api_gateway_rest_api.console.execution_arn}/*/GET/batches",
      "${aws_api_gateway_rest_api.console.execution_arn}/*/GET/batches/*",
    ]
  }

  statement {
    sid    = "DenyAllButNamedRoles"
    effect = "Deny"
    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
    actions   = ["execute-api:Invoke"]
    resources = ["${aws_api_gateway_rest_api.console.execution_arn}/*"]
    condition {
      test     = "StringNotEquals"
      variable = "aws:PrincipalArn"
      values   = local.all_named_role_arns
    }
    # OPTIONS preflight is unauthenticated by necessity; exempt it from the deny.
    condition {
      test     = "StringNotEquals"
      variable = "aws:PrincipalType"
      values   = ["Anonymous"]
    }
  }
}

resource "aws_api_gateway_rest_api_policy" "console" {
  rest_api_id = aws_api_gateway_rest_api.console.id
  policy      = data.aws_iam_policy_document.resource_policy.json
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  qualifier     = aws_lambda_alias.live.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.console.execution_arn}/*"
}

resource "aws_api_gateway_deployment" "console" {
  rest_api_id = aws_api_gateway_rest_api.console.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.proxy.id,
      aws_api_gateway_method.proxy_any.id,
      aws_api_gateway_integration.proxy_lambda.id,
      aws_api_gateway_integration.proxy_options.id,
      data.aws_iam_policy_document.resource_policy.json,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.proxy_lambda,
    aws_api_gateway_integration_response.proxy_options,
    aws_api_gateway_rest_api_policy.console,
  ]
}

resource "aws_api_gateway_stage" "this" {
  rest_api_id          = aws_api_gateway_rest_api.console.id
  deployment_id        = aws_api_gateway_deployment.console.id
  stage_name           = var.stage
  xray_tracing_enabled = true

  # Account-level API GW CloudWatch role already exists (api_intake_stage).
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId    = "$context.requestId"
      httpMethod   = "$context.httpMethod"
      resourcePath = "$context.resourcePath"
      status       = "$context.status"
      userArn      = "$context.identity.userArn"
      sourceIp     = "$context.identity.sourceIp"
    })
  }
}
