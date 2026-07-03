variable "repo_name" {
  description = "ECR repository name (lowercase; hyphens as separators)."
  type        = string
}

variable "force_delete" {
  description = "Allow deleting the repository even when it contains images. True only in dev for teardown convenience."
  type        = bool
  default     = false
}

variable "keep_last_images" {
  description = "Lifecycle policy: number of most-recent images to retain."
  type        = number
  default     = 10
}
