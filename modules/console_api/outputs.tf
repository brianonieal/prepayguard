output "api_endpoint" {
  description = "Console API base URL."
  value       = aws_api_gateway_stage.this.invoke_url
}

output "api_execution_arn" {
  description = "For the console role's invoke policy (attached at env level)."
  value       = aws_api_gateway_rest_api.console.execution_arn
}

output "function_name" {
  value = aws_lambda_function.api.function_name
}

output "uploads_bucket_name" {
  value = aws_s3_bucket.uploads.id
}
