variable "name_prefix" {
  type = string
}

variable "image_uri" {
  type = string
}

# v2.0.0/v2.1.0 role-scoped access: reviewers/admins get the API; submitters are
# edge-scoped to the batch-upload routes; reference WRITES are admin-only (the
# reviewer role is edge-denied on PUT /reference, and the handler checks too).
variable "admin_role_arn" {
  description = "Admin group role — every route, including reference-data publishes."
  type        = string
}

variable "reviewer_role_arn" {
  description = "Reviewer group role — every route EXCEPT reference-data writes."
  type        = string
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

# v2.1.0 reference-data lifecycle: console_api reads the current list and
# publishes new versions (admin-only).
variable "reference_bucket_name" {
  type = string
}

variable "reference_bucket_arn" {
  type = string
}

# v2.2.0: console_api embeds reference entries on publish (Bedrock).
variable "embed_model" {
  description = "Bedrock embedding model id (e.g. amazon.titan-embed-text-v2:0)."
  type        = string
}

variable "embed_model_arn" {
  description = "Foundation-model ARN the API may invoke for embeddings."
  type        = string
}

# v2.3.0: LLM adjudication briefs (Bedrock text model via Converse).
variable "brief_model" {
  description = "Bedrock text model id for reviewer briefs (e.g. amazon.nova-lite-v1:0)."
  type        = string
}

variable "brief_model_arn" {
  description = "Foundation-model ARN the API may invoke for briefs."
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
