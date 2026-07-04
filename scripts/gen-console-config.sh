#!/bin/bash
# Regenerate console/src/config.js from terraform outputs.
set -euo pipefail
cd "$(dirname "$0")/.."
TF="terraform -chdir=environments/dev"
cog=$($TF output -json console_cognito)
cat > console/src/config.js <<EOF
// Generated from terraform output (scripts/gen-console-config.sh). Public client
// identifiers — embedded in the SPA by design, not secrets.
export const config = {
  region: "us-east-2",
  userPoolId: "$(echo "$cog" | python -c 'import sys,json;print(json.load(sys.stdin)["user_pool_id"])')",
  userPoolClientId: "$(echo "$cog" | python -c 'import sys,json;print(json.load(sys.stdin)["client_id"])')",
  identityPoolId: "$(echo "$cog" | python -c 'import sys,json;print(json.load(sys.stdin)["identity_pool_id"])')",
  intakeApi: "$($TF output -raw api_endpoint)",
  consoleApi: "$($TF output -raw console_api_endpoint)",
};
EOF
echo "wrote console/src/config.js"
