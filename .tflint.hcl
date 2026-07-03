# tflint configuration (DEC-9). Run from repo root:
#   tflint --init          # installs the AWS ruleset plugin below
#   tflint --recursive     # lints every directory

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "aws" {
  enabled = true
  version = "0.48.0" # verified latest release at v0.1.0 gate (2026-07-03)
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}
