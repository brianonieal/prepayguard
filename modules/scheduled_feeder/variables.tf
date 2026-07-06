variable "name_prefix" {
  type = string
}

variable "image_uri" {
  type = string
}

variable "batch_bucket_name" {
  description = "Batch-imports bucket the feeder writes feed files into; Component E's ObjectCreated trigger ingests them."
  type        = string
}

variable "batch_bucket_arn" {
  type = string
}

variable "schedule_expression" {
  description = "EventBridge schedule (DEC-23: hourly). rate(1 hour) by default."
  type        = string
  default     = "rate(1 hour)"
}

variable "enabled" {
  description = "Stop switch: false disables the schedule so the feed stops cleanly (bounds immutable audit growth / cost)."
  type        = bool
  default     = true
}

variable "feed_limit" {
  description = "Max real awards pulled per run (bounds cost + permanent audit records)."
  type        = number
  default     = 10
}

variable "demo_positive_name" {
  description = "Name on the live Do Not Pay list used only by the labeled manual demo-positive invoke; never by the schedule."
  type        = string
  default     = "Globex Overseas Incorporated"
}

variable "memory_size" {
  type    = number
  default = 256
}

variable "timeout" {
  type    = number
  default = 60
}

variable "log_retention_days" {
  type    = number
  default = 365
}
