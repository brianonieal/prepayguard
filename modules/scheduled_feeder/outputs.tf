output "function_name" {
  description = "Component F function name (manual invoke / rollback ref)."
  value       = aws_lambda_function.feeder.function_name
}

output "schedule_rule_name" {
  description = "EventBridge rule name (disable to stop the feed)."
  value       = aws_cloudwatch_event_rule.schedule.name
}
