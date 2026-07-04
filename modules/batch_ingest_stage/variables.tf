variable "name_prefix" {
  type = string
}

variable "image_uri" {
  type = string
}

variable "batch_bucket_name" {
  description = "Private bucket that receives uploaded batch CSVs (presigned PUT); its ObjectCreated events trigger Component E."
  type        = string
}

# Component E reuses Component A's idempotency store + intake queue (DEC-16), so
# a payment submitted via both the single API and a batch file dedupes correctly.
variable "idempotency_table_name" {
  type = string
}

variable "idempotency_table_arn" {
  type = string
}

variable "intake_queue_url" {
  type = string
}

variable "intake_queue_arn" {
  type = string
}

variable "console_origin" {
  description = "SPA origin (CloudFront URL) allowed to PUT to the batch bucket via CORS."
  type        = string
}

variable "memory_size" {
  type    = number
  default = 512
}

variable "timeout" {
  description = "Single Lambda parses a whole file; give headroom over the single-request stages."
  type        = number
  default     = 120
}

variable "idempotency_ttl_days" {
  type    = number
  default = 7
}

variable "log_retention_days" {
  type    = number
  default = 365
}
