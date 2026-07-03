variable "name_prefix" {
  description = "Project/environment prefix for resource names (e.g. treasury-dev)."
  type        = string
}

variable "max_receive_count" {
  description = "Receives before a review item moves to the review DLQ. Higher than worker stages: human tooling may peek repeatedly."
  type        = number
  default     = 5
}

variable "visibility_timeout_seconds" {
  description = "How long a claimed review item stays invisible to other reviewers."
  type        = number
  default     = 1800 # 30 minutes — a human review session, not a Lambda timeout
}

variable "age_alarm_threshold_seconds" {
  description = "Age of the oldest unworked review item that trips the fallback alarm (DEC-7 risk note)."
  type        = number
  default     = 14400 # 4 hours
}
