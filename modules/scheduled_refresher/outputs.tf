output "function_name" {
  description = "Component G function name (manual invoke / rollback ref)."
  value       = aws_lambda_function.refresher.function_name
}

output "schedule_name" {
  description = "EventBridge Scheduler schedule name (disable / set refresher_enabled=false to stop refreshes)."
  value       = aws_scheduler_schedule.refresh.name
}
