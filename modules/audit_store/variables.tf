variable "bucket_name" {
  description = "Globally unique audit bucket name (environment appends the account ID)."
  type        = string
}

variable "retention_days" {
  description = <<-EOT
    Object Lock COMPLIANCE default retention in DAYS. Deliberately has NO
    default: choosing it is an explicit act (DEC-4 risk note — it cannot be
    shortened after an object is written, by anyone, ever). Dev uses a short
    value; the real retention (and whether to express it in days vs years —
    they are NOT interchangeable) is signed off before the v0.4.0 apply.
  EOT
  type        = number

  validation {
    condition     = var.retention_days >= 1
    error_message = "retention_days must be at least 1 (S3 Object Lock minimum)."
  }
}
