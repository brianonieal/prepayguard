output "user_pool_id" {
  value = aws_cognito_user_pool.console.id
}

output "user_pool_client_id" {
  value = aws_cognito_user_pool_client.spa.id
}

output "identity_pool_id" {
  value = aws_cognito_identity_pool.console.id
}

output "authenticated_role_arn" {
  description = "Role logged-in console users assume (added to the intake API's allowed principals)."
  value       = aws_iam_role.authenticated.arn
}

output "authenticated_role_name" {
  description = "For attaching invoke policies at env level (breaks the module reference cycle)."
  value       = aws_iam_role.authenticated.name
}

output "console_url" {
  value = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "site_bucket_name" {
  value = aws_s3_bucket.site.bucket
}

output "reviews_table_name" {
  value = aws_dynamodb_table.reviews.name
}

output "reviews_table_arn" {
  value = aws_dynamodb_table.reviews.arn
}
