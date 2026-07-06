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
  description = "EventBridge Scheduler expression. Default: top of each hour 9am-5pm, evaluated in schedule_timezone, all 7 days (DEC-23 amendment)."
  type        = string
  default     = "cron(0 9-17 * * ? *)"
}

variable "schedule_timezone" {
  description = "IANA timezone the schedule is evaluated in; America/New_York auto-tracks EST/EDT so business hours do not drift at DST."
  type        = string
  default     = "America/New_York"
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
