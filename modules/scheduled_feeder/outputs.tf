output "function_name" {
  description = "Component F function name (manual invoke / rollback ref)."
  value       = aws_lambda_function.feeder.function_name
}

output "schedule_name" {
  description = "EventBridge Scheduler schedule name (disable / set feeder_enabled=false to stop the feed)."
  value       = aws_scheduler_schedule.feed.name
}
