output "api_endpoint" {
  description = "Payment Intake API base URL (POST <api_endpoint>/payments, SigV4-signed as the payment-submitter role)."
  value       = module.api_intake.api_endpoint
}

output "payment_submitter_role_arn" {
  description = "The one role allowed to invoke the intake API (DEC-5). Test clients assume this."
  value       = aws_iam_role.payment_submitter.arn
}

output "audit_bucket_name" {
  description = "Immutable audit bucket (commitment 4)."
  value       = module.audit_store.bucket_name
}

output "audit_bucket_arn" {
  description = "Audit bucket ARN."
  value       = module.audit_store.bucket_arn
}

output "review_queue_url" {
  description = "Human-review queue (commitment 2 destination)."
  value       = module.review_queue.queue_url
}

output "webhook_secret_arn" {
  description = "Secrets Manager ARN holding the review-notification webhook URL (DEC-7). Value is set out-of-band, never via Terraform."
  value       = aws_secretsmanager_secret.review_webhook.arn
}

output "worker_function_names" {
  description = "B/C/D Lambda names, keyed by stage."
  value       = { for k, m in module.worker : k => m.function_name }
}

output "worker_dlq_urls" {
  description = "B/C/D dead-letter queues, keyed by stage (commitment 2 evidence surface)."
  value       = { for k, m in module.worker : k => m.dlq_url }
}

output "intake_function_name" {
  description = "Component A Lambda name."
  value       = module.api_intake.function_name
}

output "console_url" {
  description = "Treasury Console (CloudFront). Placeholder page until v1.3.0."
  value       = module.console.console_url
}

output "console_site_bucket" {
  description = "S3 bucket that holds the console SPA contents (scripts/deploy-console.sh syncs to it)."
  value       = module.console.site_bucket_name
}

output "console_distribution_id" {
  description = "CloudFront distribution ID for the console (scripts/deploy-console.sh invalidates it)."
  value       = module.console.distribution_id
}

output "console_cognito" {
  description = "Cognito wiring for the SPA (v1.3.0/v1.4.0)."
  value = {
    user_pool_id     = module.console.user_pool_id
    client_id        = module.console.user_pool_client_id
    identity_pool_id = module.console.identity_pool_id
  }
}

output "console_api_endpoint" {
  description = "Console read/action API base URL (v1.2.0)."
  value       = module.console_api.api_endpoint
}

output "reference_bucket_name" {
  description = "Versioned Do Not Pay reference-list bucket (scripts/seed_reference_data.py and scripts/ingest_sam_exclusions.py write to it)."
  value       = module.reference_store.bucket_name
}

output "reviews_table_name" {
  description = "Queryable review items (console dashboard source)."
  value       = module.console.reviews_table_name
}

output "ecr_repository_urls" {
  description = "Per-component ECR repository URLs, keyed by component."
  value       = { for k, m in module.ecr : k => m.repository_url }
}
