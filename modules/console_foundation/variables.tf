variable "name_prefix" {
  description = "Project/environment prefix (e.g. treasury-dev)."
  type        = string
}

variable "site_bucket_name" {
  description = "Globally unique bucket for the SPA assets (env appends account id)."
  type        = string
}
