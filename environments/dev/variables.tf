variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-2" # Ohio — matches the operator's console/account (<OPERATOR>, <ACCOUNT_ID>)
}

variable "project_name" {
  description = "Resource-name prefix root. 'treasury' is the external project name (DEC-12)."
  type        = string
  default     = "treasury"
}

variable "environment" {
  description = "Environment name, used in prefixes and the API stage."
  type        = string
  default     = "dev"
}

variable "audit_retention_days" {
  description = <<-EOT
    Object Lock COMPLIANCE default retention (days) for the audit bucket.
    NO DEFAULT ON PURPOSE: this value is irreversible per object once written
    (DEC-4). terraform.tfvars must state it explicitly, as a deliberate act.
  EOT
  type        = number
}

variable "placeholder_image_tag" {
  description = "Image tag used to form syntactically valid ECR image URIs before real images exist (v0.1.0 is plan-only; apply requires real images at each component's gate)."
  type        = string
  default     = "bootstrap"
}

variable "feeder_enabled" {
  description = "Component F (DEC-23) stop switch: false disables the hourly EventBridge schedule so the automated feed stops (bounds cost + permanent audit-record growth)."
  type        = bool
  default     = true
}

variable "refresher_enabled" {
  description = "Component G (DEC-24) stop switch: false disables the daily reference-refresh schedule."
  type        = bool
  default     = true
}

variable "payee_validation_enabled" {
  description = "Phase 2.1e (DEC-29): intake payee validation (maxLength 35 + printable-ASCII), fail-closed. Default ON. Set false (terraform -var) to restore the pre-2.1e unbounded schema so the demo can reproduce the F1 matcher-evasion attack."
  type        = bool
  default     = true
}
