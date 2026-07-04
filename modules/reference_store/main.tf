# modules/reference_store - versioned Do Not Pay screening lists (v2.1.0).
# The reference data Component B screens against stops being baked into its
# container image and lives here as a versioned S3 document:
#   reference/current.json       - the active list (what B fetches + caches)
#   reference/versions/{N}.json  - immutable history (what audit citations resolve to)
# Terraform owns the BUCKET, never the documents (same lesson as the SPA assets):
# version 1 is seeded out-of-band (scripts/seed_reference_data.py) and later
# versions are published by admins through console_api's PUT /reference.

resource "aws_s3_bucket" "reference" {
  bucket        = var.bucket_name
  force_destroy = true # dev: reference lists are re-seedable, safe to tear down
}

resource "aws_s3_bucket_public_access_block" "reference" {
  bucket                  = aws_s3_bucket.reference.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reference" {
  bucket = aws_s3_bucket.reference.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Native versioning is belt-and-braces under the explicit versions/{N}.json
# history: current.json can always be reconstructed even if a publish is botched.
resource "aws_s3_bucket_versioning" "reference" {
  bucket = aws_s3_bucket.reference.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "reference" {
  bucket = aws_s3_bucket.reference.id
  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
  # NOTE: no expiration rules on purpose - version history is the audit-citation
  # target (screenings cite "list vN"; versions/{N}.json must stay resolvable).
}
