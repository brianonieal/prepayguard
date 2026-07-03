# State backend — LOCAL for course scope (deliberate, documented).
#
# Why local: single operator (Brian), single machine, free-tier budget, and no
# team contention on state. The usual reasons to pay for remote state (locking
# across operators, CI applies) don't exist here — CI is plan-only by design
# (DEC-6; no auto-apply), so workflows never need state write access.
#
# Upgrade path if this ever becomes multi-operator: S3 backend with native
# lockfile support (Terraform >= 1.10 locks via S3 conditional writes — no
# DynamoDB table needed anymore), e.g.:
#
#   backend "s3" {
#     bucket       = "<state-bucket>"
#     key          = "treasury/dev/terraform.tfstate"
#     region       = "us-east-1"
#     use_lockfile = true
#     encrypt      = true
#   }
#
# NOTE: *.tfstate is gitignored. Local state contains resource attributes —
# never commit it.

terraform {
  backend "local" {}
}
