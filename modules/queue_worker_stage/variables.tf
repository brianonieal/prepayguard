# queue_worker_stage variables.
# Core set per the approved scaffold (DEC-1): stage_name, image_uri,
# input_queue_arn, output_queue_arn, memory_size, timeout, env_vars,
# max_concurrency, secrets_arn. Additions beyond the scaffold comment are
# documented in README.md (input_queue_url, audit_bucket_arn, name_prefix,
# tuning knobs) — each exists to keep the shared shape identical across
# B/C/D rather than to specialize any one stage.

variable "name_prefix" {
  description = "Project/environment prefix for all resource names (e.g. treasury-dev)."
  type        = string
}

variable "stage_name" {
  description = "Stage identifier: enrichment, risk_scoring, or disposition."
  type        = string
}

variable "image_uri" {
  description = "ECR container image URI for this stage's Lambda (DEC-2). Placeholder tag at v0.1.0; real digest-pinned images land at each component's gate."
  type        = string
}

variable "input_queue_arn" {
  description = "ARN of the SQS queue this stage consumes. Created upstream (previous stage or environment) — never by this module, to keep for_each instances cycle-free."
  type        = string
}

variable "input_queue_url" {
  description = "URL of the input queue. Needed because the redrive-policy attachment (aws_sqs_queue_redrive_policy) addresses queues by URL, not ARN."
  type        = string
}

variable "output_queue_arn" {
  description = "ARN of the downstream queue this stage's Lambda is allowed to send to (next stage's input; for disposition, the review queue)."
  type        = string
}

variable "memory_size" {
  description = "Lambda memory (MB)."
  type        = number
  default     = 512
}

variable "timeout" {
  description = "Lambda timeout (seconds). The input queue's visibility timeout must be at least 6x this value (AWS guidance for SQS event sources); the environment sets that on the queues it creates."
  type        = number
  default     = 30
}

variable "env_vars" {
  description = "Environment variables for the handler (queue URLs, bucket name, secret ARN, etc.)."
  type        = map(string)
  default     = {}
}

variable "max_concurrency" {
  description = "Maximum concurrent Lambda executions this queue may drive (event source mapping scaling_config). Commitment 3 lever. AWS minimum is 2."
  type        = number
  default     = 10

  validation {
    condition     = var.max_concurrency >= 2 && var.max_concurrency <= 1000
    error_message = "max_concurrency must be between 2 and 1000 (AWS SQS event-source scaling limits)."
  }
}

variable "batch_size" {
  description = "Messages per Lambda invocation batch."
  type        = number
  default     = 10
}

variable "maximum_batching_window_in_seconds" {
  description = "How long to gather a batch before invoking. 0 = invoke as soon as messages arrive."
  type        = number
  default     = 0
}

variable "max_receive_count" {
  description = "Receives before a message is moved to the DLQ (commitment 2). Low by design: a payment that fails 3 processing attempts needs human eyes, not more retries."
  type        = number
  default     = 3

  validation {
    condition     = var.max_receive_count >= 1 && var.max_receive_count <= 1000
    error_message = "max_receive_count must be between 1 and 1000."
  }
}

variable "secrets_arn" {
  description = "DEC-7: ARN of the single Secrets Manager secret this stage may read. Null for every stage except disposition (Component D), whose instance sets it to the review-webhook secret. Controls a conditional IAM statement."
  type        = string
  default     = null
}

variable "audit_bucket_arn" {
  description = "Commitment 4: ARN of the S3 Object Lock audit bucket this stage may write to. Null for every stage except disposition (Component D). Controls a conditional IAM statement."
  type        = string
  default     = null
}

variable "reviews_table_arn" {
  description = "Console v1.1.0: ARN of the reviews DynamoDB table Component D writes review items to. Null for every other stage. Controls a conditional IAM statement."
  type        = string
  default     = null
}

variable "audit_kms_key_arn" {
  description = "ARN of the CMK encrypting the audit bucket. Set together with audit_bucket_arn (Component D only): SSE-KMS writes require key usage rights on the writer principal."
  type        = string
  default     = null
}

variable "queue_depth_alarm_threshold" {
  description = "ApproximateNumberOfMessagesVisible level that trips the queue-depth alarm (commitment 3 signal)."
  type        = number
  default     = 100
}

variable "alarm_evaluation_periods" {
  description = "Consecutive 60s periods the depth threshold must hold before alarming."
  type        = number
  default     = 2
}

variable "log_retention_days" {
  description = "CloudWatch log retention. 365 satisfies CKV_AWS_338 (>= 1 year) at negligible cost for course volumes."
  type        = number
  default     = 365
}
