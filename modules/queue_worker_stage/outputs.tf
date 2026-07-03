output "function_arn" {
  description = "Unqualified Lambda function ARN."
  value       = aws_lambda_function.worker.arn
}

output "function_name" {
  description = "Lambda function name."
  value       = aws_lambda_function.worker.function_name
}

output "alias_arn" {
  description = "ARN of the 'live' alias (DEC-10 rollback pointer). Event source mapping is bound to this."
  value       = aws_lambda_alias.live.arn
}

output "dlq_arn" {
  description = "Dead-letter queue ARN (commitment 2 evidence surface)."
  value       = aws_sqs_queue.dlq.arn
}

output "dlq_url" {
  description = "Dead-letter queue URL (used by failure-routing tests)."
  value       = aws_sqs_queue.dlq.url
}

output "output_queue_arn" {
  description = "Pass-through of the downstream queue ARN this stage sends to (scaffold-compatible convenience)."
  value       = var.output_queue_arn
}

output "role_name" {
  description = "Execution role name (used by least-privilege IAM tests)."
  value       = aws_iam_role.worker.name
}

output "role_arn" {
  description = "Execution role ARN."
  value       = aws_iam_role.worker.arn
}

output "queue_depth_alarm_name" {
  description = "Queue-depth alarm name (commitment 3 evidence surface)."
  value       = aws_cloudwatch_metric_alarm.queue_depth.alarm_name
}
