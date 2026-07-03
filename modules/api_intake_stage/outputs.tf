output "api_id" {
  description = "REST API id."
  value       = aws_api_gateway_rest_api.intake.id
}

output "api_execution_arn" {
  description = "Execution ARN base (used for execute-api:Invoke identity policies, e.g. the payment-submitter role)."
  value       = aws_api_gateway_rest_api.intake.execution_arn
}

output "api_endpoint" {
  description = "Invoke URL of the deployed stage — POST <api_endpoint>/payments."
  value       = aws_api_gateway_stage.this.invoke_url
}

output "function_arn" {
  description = "Intake Lambda function ARN."
  value       = aws_lambda_function.intake.arn
}

output "function_name" {
  description = "Intake Lambda function name."
  value       = aws_lambda_function.intake.function_name
}

output "alias_arn" {
  description = "ARN of the 'live' alias (DEC-10 rollback pointer)."
  value       = aws_lambda_alias.live.arn
}

output "output_queue_arn" {
  description = "A→B queue ARN (Component B's input_queue_arn)."
  value       = aws_sqs_queue.output.arn
}

output "output_queue_url" {
  description = "A→B queue URL (Component B's input_queue_url; also A's handler env var)."
  value       = aws_sqs_queue.output.url
}

output "role_name" {
  description = "Execution role name (used by least-privilege IAM tests)."
  value       = aws_iam_role.intake.name
}
