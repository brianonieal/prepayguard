variable "name_prefix" {
  description = "Project/environment prefix for resource names (e.g. treasury-dev)."
  type        = string
}

variable "image_uri" {
  description = "ECR container image URI for the intake Lambda (placeholder tag at v0.1.0)."
  type        = string
}

variable "allowed_invoker_role_arn" {
  description = "DEC-5: the ONE IAM role ARN permitted to invoke the API. The resource policy denies every other principal."
  type        = string
}

variable "stage" {
  description = "API Gateway stage name (matches the environment: dev)."
  type        = string
  default     = "dev"
}

variable "memory_size" {
  description = "Lambda memory (MB)."
  type        = number
  default     = 512
}

variable "timeout" {
  description = "Lambda timeout (seconds). API Gateway's own integration timeout is 29s; keep at or below it."
  type        = number
  default     = 29
}

variable "env_vars" {
  description = "Environment variables for the intake handler (output queue URL; idempotency store config arrives at v0.2.0)."
  type        = map(string)
  default     = {}
}

variable "output_queue_visibility_timeout" {
  description = "Visibility timeout on the A→B queue. Must be >= 6x Component B's Lambda timeout (AWS guidance for SQS event sources); the environment computes and passes this."
  type        = number
  default     = 360
}

variable "log_retention_days" {
  description = "CloudWatch log retention for both the Lambda and API access-log groups."
  type        = number
  default     = 365
}

variable "idempotency_read_capacity" {
  description = "Provisioned RCU for the idempotency dedup table. Low by design (dedup cache); stays within DynamoDB free tier."
  type        = number
  default     = 5
}

variable "idempotency_write_capacity" {
  description = "Provisioned WCU for the idempotency dedup table."
  type        = number
  default     = 5
}
