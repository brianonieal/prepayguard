variable "name_prefix" {
  type = string
}

variable "image_uri" {
  type = string
}

# v2.0.0 role-scoped access: reviewers/admins get the whole API; submitters are
# scoped (at the edge) to the batch-upload routes only.
variable "reviewer_admin_role_arns" {
  description = "Roles allowed to invoke every route (reviewer + admin)."
  type        = list(string)
}

variable "submitter_role_arn" {
  description = "Submitter role — admitted ONLY on the batch-upload routes (POST/GET /batches)."
  type        = string
}

variable "reviews_table_name" {
  type = string
}

variable "reviews_table_arn" {
  type = string
}

variable "reviews_status_index_arn" {
  type = string
}

variable "audit_index_table_name" {
  type = string
}

variable "audit_index_table_arn" {
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

# v1.6.0 write-scale: batch CSV ingestion. console_api presigns the upload and
# reads the batch summary written by Component E.
variable "batch_bucket_name" {
  type = string
}

variable "batch_bucket_arn" {
  type = string
}

variable "batches_table_name" {
  type = string
}

variable "batches_table_arn" {
  type = string
}

variable "stage" {
  type    = string
  default = "dev"
}

variable "log_retention_days" {
  type    = number
  default = 365
}
