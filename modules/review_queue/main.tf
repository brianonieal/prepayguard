# modules/review_queue — the human-review path (commitment 2's destination).
# Component D sends ambiguous dispositions here; humans drain it (console or
# future tooling) — deliberately NO consumer Lambda or event source mapping.
# The age alarm is the DEC-7 fallback: if the webhook notification path fails,
# an item sitting unworked still surfaces.

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name_prefix}-review-dlq"
  message_retention_seconds = 1209600 # 14 days (SQS maximum)
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "review" {
  name = "${var.name_prefix}-review"
  # Humans are slower than Lambdas: maximum retention so review items survive
  # a slow week without silent expiry.
  message_retention_seconds  = 1209600
  visibility_timeout_seconds = var.visibility_timeout_seconds
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.url

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.review.arn]
  })
}

# DEC-7 risk-note fallback: alarm when the oldest review item exceeds the age
# threshold — catches a dead webhook without depending on the webhook.
resource "aws_cloudwatch_metric_alarm" "oldest_item_age" {
  alarm_name          = "${var.name_prefix}-review-oldest-item-age"
  alarm_description   = "Oldest human-review item exceeds ${var.age_alarm_threshold_seconds}s (DEC-7 webhook-failure fallback)"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.age_alarm_threshold_seconds
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.review.name
  }
}
