output "bucket_name" {
  description = "Reference-data bucket (B reads current.json; console_api publishes versions)."
  value       = aws_s3_bucket.reference.id
}

output "bucket_arn" {
  value = aws_s3_bucket.reference.arn
}
