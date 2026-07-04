variable "name_prefix" {
  type = string
}

variable "image_uri" {
  type = string
}

variable "allowed_invoker_role_arn" {
  description = "The console authenticated role — the ONLY principal that may invoke this API."
  type        = string
}

variable "reviews_table_name" {
  type = string
}

variable "reviews_table_arn" {
  type = string
}

variable "audit_bucket_name" {
  type = string
}

variable "audit_bucket_arn" {
  type = string
}

variable "audit_kms_key_arn" {
  type = string
}

variable "console_origin" {
  description = "The SPA origin (CloudFront URL) allowed by CORS."
  type        = string
}

variable "uploads_bucket_name" {
  description = "Private bucket for reviewer case-document uploads (presigned PUT)."
  type        = string
}

variable "stage" {
  type    = string
  default = "dev"
}

variable "log_retention_days" {
  type    = number
  default = 365
}
