#!/bin/bash
# Build + deploy the Treasury Console SPA to S3 + CloudFront.
# Terraform owns the bucket/distribution; this owns their CONTENTS.
#
# The bucket, distribution, and URL are resolved from `terraform output`, so this
# script is account-agnostic: it works against whatever account/region the state
# in environments/dev points at (no hardcoded account id, bucket, or domain).
set -euo pipefail
cd "$(dirname "$0")/.."

TF="terraform -chdir=environments/dev"

# Preflight: console_site_bucket / console_distribution_id are read from state. They
# were added as outputs in v3.7.2, so a deployment last applied before then will not
# have them in state yet. Fail with a clear, actionable message instead of a bare
# "Output not found" from terraform.
tf_out() {
  local name="$1" val
  if ! val=$($TF output -raw "$name" 2>/dev/null) || [ -z "$val" ]; then
    echo "ERROR: terraform output '$name' is not in state." >&2
    echo "Run 'terraform -chdir=environments/dev apply' once to publish the v3.7.2" >&2
    echo "console outputs (a state-only change, no new resources), then retry." >&2
    exit 1
  fi
  printf '%s' "$val"
}

SITE=$(tf_out console_site_bucket)
DIST=$(tf_out console_distribution_id)
URL=$(tf_out console_url)

echo "→ config from terraform outputs"
bash scripts/gen-console-config.sh

echo "→ build"
( cd console && npm ci --no-fund --no-audit && npm run build )

echo "→ sync to s3://$SITE"
# hashed assets get long cache; index.html must never be stale.
aws s3 sync console/dist "s3://$SITE" --delete \
  --exclude index.html --cache-control "public,max-age=31536000,immutable"
aws s3 cp console/dist/index.html "s3://$SITE/index.html" \
  --cache-control "no-cache" --content-type "text/html"

echo "→ invalidate CloudFront ($DIST)"
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" \
  --query 'Invalidation.Status' --output text
echo "done → $URL"
