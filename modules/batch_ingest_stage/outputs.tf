output "batch_bucket_name" {
  description = "Batch-imports bucket (console presigns PUTs here)."
  value       = aws_s3_bucket.batch.id
}

output "batch_bucket_arn" {
  value = aws_s3_bucket.batch.arn
}

output "batches_table_name" {
  description = "Batch summary table (console polls GET /batches/{id})."
  value       = aws_dynamodb_table.batches.name
}

output "batches_table_arn" {
  value = aws_dynamodb_table.batches.arn
}

output "function_name" {
  description = "Component E function name (deploy/rollback ref)."
  value       = aws_lambda_function.batch.function_name
}
