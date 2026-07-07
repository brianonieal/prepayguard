variable "name_prefix" {
  type = string
}

variable "image_uri" {
  type = string
}

variable "reference_bucket_name" {
  description = "Versioned reference-store bucket the refresher reads current.json from and publishes new versions to."
  type        = string
}

variable "reference_bucket_arn" {
  type = string
}

variable "embed_model" {
  description = "Bedrock embedding model id used to re-embed refreshed SAM entries (DEC-19)."
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "embed_model_arn" {
  description = "ARN of the embedding foundation model, to scope bedrock:InvokeModel."
  type        = string
}

variable "refresh_limit" {
  description = "Cap on real SAM entries pulled per refresh (in-store-cosine budget, DEC-19)."
  type        = number
  default     = 90
}

variable "schedule_expression" {
  description = "EventBridge Scheduler expression. Default: once daily at 6am, in schedule_timezone (SAM publishes daily)."
  type        = string
  default     = "cron(0 6 * * ? *)"
}

variable "schedule_timezone" {
  description = "IANA timezone the schedule is evaluated in; America/New_York auto-tracks EST/EDT."
  type        = string
  default     = "America/New_York"
}

variable "enabled" {
  description = "Stop switch: false disables the daily refresh schedule."
  type        = bool
  default     = true
}

variable "memory_size" {
  description = "Higher than the feeder: downloads the SAM CSV and computes ~90 Titan embeddings per run."
  type        = number
  default     = 512
}

variable "timeout" {
  type    = number
  default = 300
}

variable "log_retention_days" {
  type    = number
  default = 365
}
