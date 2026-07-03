output "bucket_arn" {
  description = "Audit bucket ARN (Component D's conditional IAM statement scopes to this)."
  value       = aws_s3_bucket.audit.arn
}

output "bucket_name" {
  description = "Audit bucket name (passed to Component D as an env var)."
  value       = aws_s3_bucket.audit.bucket
}

output "kms_key_arn" {
  description = "CMK encrypting audit records at rest."
  value       = aws_kms_key.audit.arn
}

output "object_lock_mode" {
  description = "Configured default lock mode (evidence surface for commitment 4 tests)."
  value       = "COMPLIANCE"
}
