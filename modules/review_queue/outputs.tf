output "queue_arn" {
  description = "Review queue ARN — Component D's output_queue_arn."
  value       = aws_sqs_queue.review.arn
}

output "queue_url" {
  description = "Review queue URL (passed to Component D as an env var; used by tests and human tooling)."
  value       = aws_sqs_queue.review.url
}

output "dlq_arn" {
  description = "Review DLQ ARN."
  value       = aws_sqs_queue.dlq.arn
}

output "age_alarm_name" {
  description = "Fallback age alarm name (DEC-7 evidence surface)."
  value       = aws_cloudwatch_metric_alarm.oldest_item_age.alarm_name
}
