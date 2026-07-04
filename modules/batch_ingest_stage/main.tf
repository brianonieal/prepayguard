# modules/batch_ingest_stage - Component E: S3-triggered bulk payment intake
# (v1.6.0, write-scale). A CSV uploaded to the batch-imports bucket fires an
# ObjectCreated event; Component E parses each row and performs the SAME
# payment-ID idempotency claim + enqueue as Component A (DEC-13/DEC-16),
# against the SAME idempotency table and intake queue passed in from
# api_intake_stage. No API Gateway here - the trigger is S3, not HTTP.

locals {
  function_name = "${var.name_prefix}-batch-ingest"
}

data "aws_caller_identity" "current" {}

# ---------------------------------------------------------------------------
# Batch-imports bucket: browser PUTs the CSV via a presigned URL (needs CORS);
# private, encrypted, versioned, short lifecycle - same posture as the console
# uploads bucket. This is a transient inbox, not an audit store.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "batch" {
  bucket        = var.batch_bucket_name
  force_destroy = true # dev: teardown with objects present
}

resource "aws_s3_bucket_public_access_block" "batch" {
  bucket                  = aws_s3_bucket.batch.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "batch" {
  bucket = aws_s3_bucket.batch.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "batch" {
  bucket = aws_s3_bucket.batch.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "batch" {
  bucket = aws_s3_bucket.batch.id
  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
  rule {
    id     = "expire-raw-uploads"
    status = "Enabled"
    filter {}
    # The CSV inbox is disposable once ingested; the audit record is Component D's.
    expiration {
      days = 30
    }
    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "batch" {
  bucket = aws_s3_bucket.batch.id
  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT"]
    allowed_origins = [var.console_origin]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# ---------------------------------------------------------------------------
# Batch summary table: one item per uploaded file (counts + per-row errors),
# polled by the console. batch_id is minted by console_api at presign time and
# recovered by E from the object key, so writes are idempotent on reprocess.
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "batches" {
  name         = "${var.name_prefix}-batches"
  billing_mode = "PROVISIONED"
  hash_key     = "batch_id"

  read_capacity  = 5
  write_capacity = 5

  attribute {
    name = "batch_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true # CKV_AWS_28
  }

  server_side_encryption {
    enabled = true # AWS-managed key; CKV_AWS_119 (CMK) justified-skip in .checkov.yaml
  }
}

# ---------------------------------------------------------------------------
# IAM - least privilege: read the uploaded object, drive the SHARED idempotency
# store, enqueue to the SHARED intake queue, write the batch summary.
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

resource "aws_iam_role" "batch" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

data "aws_iam_policy_document" "batch" {
  statement {
    sid       = "WriteLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.batch.arn}:*"]
  }

  statement {
    sid       = "ReadUploadedBatch"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.batch.arn}/*"]
  }

  # Same three actions on the SAME idempotency table as Component A (DEC-16).
  statement {
    sid       = "IdempotencyStore"
    effect    = "Allow"
    actions   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [var.idempotency_table_arn]
  }

  statement {
    sid       = "EnqueueToIntake"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [var.intake_queue_arn]
  }

  statement {
    sid       = "WriteBatchSummary"
    effect    = "Allow"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.batches.arn]
  }

  statement {
    sid       = "XRayTracing"
    effect    = "Allow"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "batch" {
  name   = "${local.function_name}-policy"
  role   = aws_iam_role.batch.id
  policy = data.aws_iam_policy_document.batch.json
}

# ---------------------------------------------------------------------------
# Lambda - container image, versioned + aliased (DEC-2, DEC-10)
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "batch" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "batch" {
  function_name = local.function_name
  role          = aws_iam_role.batch.arn
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
      IDEMPOTENCY_TABLE    = var.idempotency_table_name
      OUTPUT_QUEUE_URL     = var.intake_queue_url
      BATCHES_TABLE        = aws_dynamodb_table.batches.name
      IDEMPOTENCY_TTL_DAYS = tostring(var.idempotency_ttl_days)
    }
  }

  depends_on = [aws_cloudwatch_log_group.batch, aws_iam_role_policy.batch]
}

resource "aws_lambda_alias" "live" {
  name             = "live"
  description      = "Rollback pointer (DEC-10): repoint to a prior version to roll back."
  function_name    = aws_lambda_function.batch.function_name
  function_version = aws_lambda_function.batch.version
}

# ---------------------------------------------------------------------------
# S3 -> Lambda trigger. Permission first (bucket notification requires it),
# then wire ObjectCreated on the batch-imports/ prefix to the 'live' alias so
# DEC-10 rollback covers the ingest path too.
# ---------------------------------------------------------------------------

resource "aws_lambda_permission" "allow_s3" {
  statement_id   = "AllowS3Invoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.batch.function_name
  qualifier      = aws_lambda_alias.live.name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.batch.arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_s3_bucket_notification" "batch" {
  bucket = aws_s3_bucket.batch.id

  lambda_function {
    lambda_function_arn = aws_lambda_alias.live.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "batch-imports/"
    # v2.1.2: no suffix filter - E handles CSV/XLSX/JSON and reports anything
    # else as "unsupported", so every uploaded file must reach it.
  }

  depends_on = [aws_lambda_permission.allow_s3]
}
