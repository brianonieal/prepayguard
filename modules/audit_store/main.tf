# modules/audit_store — the immutable audit log (DEC-4, graded commitment 4).
#
# ============================= IRREVERSIBILITY =============================
# S3 Object Lock COMPLIANCE mode is the one genuinely irreversible surface in
# this project:
#   - object_lock_enabled can ONLY be set at bucket creation (ForceNew).
#   - Once an object version is written under COMPLIANCE retention, NO
#     principal — including the account root — can shorten or remove that
#     retention, and AWS Support cannot override it. Retention can be
#     lengthened, never reduced.
#   - The default retention below applies to every NEW write from the moment
#     it is configured. It is not retroactive, but there is no undo for any
#     object written under it: get the value right BEFORE the first write.
#   - retention units matter: `days = 2555` and `years = 7` produce DIFFERENT
#     retain-until dates (leap days). Exactly one of days/years may be set;
#     pick the unit deliberately when the real retention is chosen.
# Dev environments use a short retention (see environments/dev/terraform.tfvars)
# so experiments don't strand objects; the real retention value is a deliberate
# sign-off before the first production-shaped write (scheduled before the
# v0.4.0 apply).
# ===========================================================================

resource "aws_s3_bucket" "audit" {
  bucket = var.bucket_name

  # Must be true at creation; cannot be retrofitted onto an existing bucket.
  object_lock_enabled = true

  # Refuse `terraform destroy` on a non-empty audit bucket. With COMPLIANCE
  # retention active, locked versions cannot be deleted anyway; this keeps
  # Terraform from trying and half-destroying state.
  force_destroy = false
}

# Versioning is REQUIRED for Object Lock and must be Enabled (never suspended).
resource "aws_s3_bucket_versioning" "audit" {
  bucket = aws_s3_bucket.audit.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Default retention: every new object version is locked in COMPLIANCE mode for
# var.retention_days with no per-request headers needed from Component D.
resource "aws_s3_bucket_object_lock_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id

  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = var.retention_days
    }
  }

  # Versioning must be Enabled before lock configuration lands.
  depends_on = [aws_s3_bucket_versioning.audit]
}

# ---------------------------------------------------------------------------
# Encryption — SSE-KMS with a customer-managed key, rotation on (CKV_AWS_145).
# An audit log of payment dispositions warrants a CMK: key usage is itself
# CloudTrail-auditable, and the key can be scoped/revoked independently.
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

# Explicit key policy (CKV2_AWS_64): the standard enable-IAM-policies root
# statement. Access to the key is then governed by scoped identity policies —
# Component D's conditional statement in queue_worker_stage grants exactly
# GenerateDataKey/Decrypt on this one key; nothing else touches it.
data "aws_iam_policy_document" "audit_key" {
  # checkov:skip=CKV_AWS_109:KMS KEY policy — "*" resource legally means THIS key; the root kms:* statement is AWS's canonical enable-IAM-policies pattern (prevents key orphaning). Grants to principals happen via scoped identity policies only.
  # checkov:skip=CKV_AWS_111:Same key-policy semantics as above — not an identity policy with unconstrained write.
  # checkov:skip=CKV_AWS_356:Key policies cannot reference any resource other than the key itself; "*" is the only valid form here.
  statement {
    sid    = "EnableRootAccountAndIamPolicies"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions   = ["kms:*"]
    resources = ["*"] # in a key policy, "*" means THIS key
  }
}

resource "aws_kms_key" "audit" {
  description             = "CMK for ${var.bucket_name} (audit log at-rest encryption)"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.audit_key.json
}

resource "aws_kms_alias" "audit" {
  name          = "alias/${var.bucket_name}"
  target_key_id = aws_kms_key.audit.key_id
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.audit.arn
    }
    bucket_key_enabled = true # cuts KMS request costs on high-write buckets
  }
}

# ---------------------------------------------------------------------------
# Lifecycle hygiene (CKV2_AWS_61). S3 lifecycle NEVER removes a version still
# under COMPLIANCE retention — expiration is deferred until the lock expires —
# so these rules are safe under any retention value.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket_lifecycle_configuration" "audit" {
  bucket = aws_s3_bucket.audit.id

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"

    filter {} # all objects

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "expire-noncurrent-versions-after-lock"
    status = "Enabled"

    filter {}

    # Takes effect only once a version's COMPLIANCE retention has expired.
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  depends_on = [aws_s3_bucket_versioning.audit]
}

# ---------------------------------------------------------------------------
# Public access: fully blocked. An audit log has no public read story, ever.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket_public_access_block" "audit" {
  bucket = aws_s3_bucket.audit.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# Bucket policy: two defensive denies.
#   1. DenyInsecureTransport — no plaintext access paths to audit data.
#   2. DenyNonComplianceLockWrites — belt-and-braces for commitment 4: even a
#      caller who explicitly sets lock headers cannot write anything weaker
#      than COMPLIANCE. Header-less writes (Component D's normal path) pass
#      through and inherit the COMPLIANCE default above; the IfExists condition
#      only bites when a caller tries to override the mode downward.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "audit_bucket" {
  # checkov:skip=CKV_AWS_93: The only wildcard-principal statements are conditional Denies (TLS-only access, lock-mode floor). Neither denies all access to the account owner, so this is not a lockout policy; flagged as a Checkov false positive during the v0.1.0 grounding review.
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    resources = [
      aws_s3_bucket.audit.arn,
      "${aws_s3_bucket.audit.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid     = "DenyNonComplianceLockWrites"
    effect  = "Deny"
    actions = ["s3:PutObject"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    resources = ["${aws_s3_bucket.audit.arn}/*"]

    condition {
      test     = "StringNotEqualsIfExists"
      variable = "s3:object-lock-mode"
      values   = ["COMPLIANCE"]
    }
  }
}

resource "aws_s3_bucket_policy" "audit" {
  bucket = aws_s3_bucket.audit.id
  policy = data.aws_iam_policy_document.audit_bucket.json

  # Public-access-block must exist before a policy referencing the bucket, or
  # concurrent creation can race BlockPublicPolicy evaluation.
  depends_on = [aws_s3_bucket_public_access_block.audit]
}
