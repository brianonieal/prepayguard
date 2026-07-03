terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0" # all module syntax verified against the v5 resource split (v0.1.0 grounding review)
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "Treasury"
      Codename    = "PrePayGuard"
      Course      = "CO.EN.AIE.LLL.2026.01"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
