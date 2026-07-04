#!/bin/bash
# Build + deploy the Treasury Console SPA to S3 + CloudFront.
# Terraform owns the bucket/distribution; this owns their CONTENTS.
set -euo pipefail
cd "$(dirname "$0")/.."

SITE="treasury-dev-console-<ACCOUNT_ID>"
DIST=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?DomainName=='d2rbxaf6pqgvb1.cloudfront.net'].Id" --output text)

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
echo "done → https://d2rbxaf6pqgvb1.cloudfront.net"
