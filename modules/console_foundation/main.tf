# modules/console_foundation — Treasury Console groundwork (Phase 2, v1.1.0).
# Cognito (human auth → temp IAM creds → SigV4, reusing the DEC-5 IAM-auth
# mechanism for the human surface), S3+CloudFront hosting shell, and the
# queryable `reviews` table the dashboard lists (SQS stays the durable hand-off;
# this table is the read/update view).
#
# NOTE: the authenticated role's execute-api:Invoke policy is attached at the
# ENVIRONMENT level, not here — the console needs the API's execution ARN and
# the API's resource policy needs this role's ARN; attaching the policy in the
# env breaks that reference cycle (same class of issue as PAT-T1).

# ---------------------------------------------------------------------------
# Cognito — User Pool (who you are) + Identity Pool (temp AWS creds)
# ---------------------------------------------------------------------------

resource "aws_cognito_user_pool" "console" {
  name = "${var.name_prefix}-console"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # Operator-managed users only: reviewers are provisioned, they don't sign up.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }
}

resource "aws_cognito_user_pool_client" "spa" {
  name         = "${var.name_prefix}-console-spa"
  user_pool_id = aws_cognito_user_pool.console.id

  # Public SPA client: no secret. SRP is the browser flow (Amplify); USER_PASSWORD
  # is also enabled so headless e2e / test clients can authenticate (DEC-15).
  generate_secret     = false
  explicit_auth_flows = ["ALLOW_USER_SRP_AUTH", "ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]

  prevent_user_existence_errors = "ENABLED"
}

resource "aws_cognito_identity_pool" "console" {
  identity_pool_name               = "${var.name_prefix}-console"
  allow_unauthenticated_identities = false

  cognito_identity_providers {
    client_id               = aws_cognito_user_pool_client.spa.id
    provider_name           = aws_cognito_user_pool.console.endpoint
    server_side_token_check = true
  }
}

# The role a logged-in human gets. Its invoke permissions are attached at env
# level (see module NOTE above).
data "aws_iam_policy_document" "authenticated_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = ["cognito-identity.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "cognito-identity.amazonaws.com:aud"
      values   = [aws_cognito_identity_pool.console.id]
    }

    condition {
      test     = "ForAnyValue:StringLike"
      variable = "cognito-identity.amazonaws.com:amr"
      values   = ["authenticated"]
    }
  }
}

resource "aws_iam_role" "authenticated" {
  name               = "${var.name_prefix}-console-authenticated"
  description        = "Fallback role for a logged-in user in NO group: no API access (v2.0.0)."
  assume_role_policy = data.aws_iam_policy_document.authenticated_assume.json
}

# v2.0.0 — per-group roles for segregation of duties. Same federated trust as
# the authenticated fallback; their distinct invoke policies are attached at env
# level (module NOTE above). submitter can submit, reviewer can adjudicate,
# admin does both (+ future reference-data / analytics surfaces).
resource "aws_iam_role" "submitter" {
  name               = "${var.name_prefix}-console-submitter"
  description        = "Console 'submitter' group: submit payments + upload batches, no approval."
  assume_role_policy = data.aws_iam_policy_document.authenticated_assume.json
}

resource "aws_iam_role" "reviewer" {
  name               = "${var.name_prefix}-console-reviewer"
  description        = "Console 'reviewer' group: adjudicate the human-review queue."
  assume_role_policy = data.aws_iam_policy_document.authenticated_assume.json
}

resource "aws_iam_role" "admin" {
  name               = "${var.name_prefix}-console-admin"
  description        = "Console 'admin' group: full console access."
  assume_role_policy = data.aws_iam_policy_document.authenticated_assume.json
}

# Cognito groups → roles. Lower precedence wins when a user is in several groups,
# so admin (10) > reviewer (20) > submitter (30) resolves cognito:preferred_role.
resource "aws_cognito_user_group" "submitter" {
  name         = "submitter"
  user_pool_id = aws_cognito_user_pool.console.id
  role_arn     = aws_iam_role.submitter.arn
  precedence   = 30
}

resource "aws_cognito_user_group" "reviewer" {
  name         = "reviewer"
  user_pool_id = aws_cognito_user_pool.console.id
  role_arn     = aws_iam_role.reviewer.arn
  precedence   = 20
}

resource "aws_cognito_user_group" "admin" {
  name         = "admin"
  user_pool_id = aws_cognito_user_pool.console.id
  role_arn     = aws_iam_role.admin.arn
  precedence   = 10
}

resource "aws_cognito_identity_pool_roles_attachment" "console" {
  identity_pool_id = aws_cognito_identity_pool.console.id

  roles = {
    # A logged-in user in NO group falls back here (no API-invoke policy attached).
    authenticated = aws_iam_role.authenticated.arn
  }

  # Map the caller to their group's role from the token's cognito:preferred_role
  # (Cognito sets it from the highest-precedence group that has a role_arn).
  role_mapping {
    identity_provider         = "${aws_cognito_user_pool.console.endpoint}:${aws_cognito_user_pool_client.spa.id}"
    type                      = "Token"
    ambiguous_role_resolution = "AuthenticatedRole"
  }
}

# ---------------------------------------------------------------------------
# Hosting shell — private S3 + CloudFront (OAC). Placeholder page until v1.3.0.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "site" {
  bucket        = var.site_bucket_name
  force_destroy = true # static assets only; safe to tear down
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${var.name_prefix}-console-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Explicit security headers (CKV2_AWS_32 requires the resource, not a managed-policy id).
resource "aws_cloudfront_response_headers_policy" "security" {
  name = "${var.name_prefix}-console-security-headers"

  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
    xss_protection {
      protection = true
      mode_block = true
      override   = true
    }
  }
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  comment             = "${var.name_prefix} Treasury Console"
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "s3-site"
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id       = "s3-site"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    # AWS managed CachingOptimized policy
    cache_policy_id            = "658327ea-f89d-4fab-a63d-7e88639e58f6"
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
  }

  restrictions {
    geo_restriction {
      # US-only console (CKV_AWS_374): single-operator course demo of a US
      # Treasury pattern; no non-US access story.
      restriction_type = "whitelist"
      locations        = ["US"]
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

data "aws_iam_policy_document" "site_bucket" {
  statement {
    sid     = "AllowCloudFrontOAC"
    effect  = "Allow"
    actions = ["s3:GetObject"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    resources = ["${aws_s3_bucket.site.arn}/*"]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket     = aws_s3_bucket.site.id
  policy     = data.aws_iam_policy_document.site_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.site]
}

# NOTE: the SPA assets (index.html + assets/) are deployed by `aws s3 sync`
# (scripts/deploy-console.sh), NOT managed by Terraform — otherwise apply would
# revert index.html to a placeholder. Terraform owns the bucket, not its contents.

# ---------------------------------------------------------------------------
# Reviews table — the dashboard's queryable view of human-review items
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "reviews" {
  name           = "${var.name_prefix}-reviews"
  billing_mode   = "PROVISIONED"
  hash_key       = "payment_id"
  read_capacity  = 5
  write_capacity = 5

  attribute {
    name = "payment_id"
    type = "S"
  }
  attribute {
    name = "status"
    type = "S"
  }
  attribute {
    name = "received_at"
    type = "S"
  }

  # v1.5.0: query pending items by age without a full-table Scan.
  global_secondary_index {
    name            = "status-received_at-index"
    hash_key        = "status"
    range_key       = "received_at"
    projection_type = "ALL"
    read_capacity   = 5
    write_capacity  = 5
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# v1.5.0: payment_id -> audit S3 key, so GET /audit is O(1) instead of an S3
# prefix scan. Component D writes one entry per disposition.
resource "aws_dynamodb_table" "audit_index" {
  name           = "${var.name_prefix}-audit-index"
  billing_mode   = "PROVISIONED"
  hash_key       = "payment_id"
  read_capacity  = 5
  write_capacity = 5

  attribute {
    name = "payment_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}
