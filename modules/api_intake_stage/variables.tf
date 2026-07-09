variable "name_prefix" {
  description = "Project/environment prefix for resource names (e.g. treasury-dev)."
  type        = string
}

variable "image_uri" {
  description = "ECR container image URI for the intake Lambda (placeholder tag at v0.1.0)."
  type        = string
}

variable "allowed_invoker_role_arns" {
  description = "DEC-5 mechanism, list form (v1.1.0): the named IAM roles permitted to invoke the API (payment-submitter + the console authenticated role). The resource policy denies every other principal."
  type        = list(string)
}

variable "stage" {
  description = "API Gateway stage name (matches the environment: dev)."
  type        = string
  default     = "dev"
}

variable "console_origin" {
  description = "SPA origin (CloudFront URL) for CORS on the intake endpoint (v1.4.0)."
  type        = string
  default     = "*"
}

variable "payee_validation_enabled" {
  description = "Phase 2.1e (DEC-29): enforce payee length + printable-ASCII validation at intake, fail-closed. Default ON. Set false to restore the pre-2.1e unbounded payee schema for the demo/attack reproduction. Toggles both the API Gateway request model and the Component A handler together."
  type        = bool
  default     = true
}

variable "payee_max_length" {
  description = "Phase 2.1e (DEC-29): max payee length. Sized to the Fedwire 35-char beneficiary-name field; 35 chosen over NACHA's 22 to minimize the cap's own cost (2.1d: a 22-char cap misses 8/96 listed entities if truncating, or bounces 29/96 legit long names if rejecting; 35 -> 2/96 or 11/96)."
  type        = number
  default     = 35
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
