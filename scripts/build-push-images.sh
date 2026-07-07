#!/bin/bash
# Build every component's Lambda container image and push it to its ECR repo at the
# tag Terraform expects. Account, region, and repository URLs are resolved from
# `terraform output`, so this script is account-agnostic (works against whatever
# account/region the state in environments/dev points at).
#
# IMPORTANT (DEC-10 + ECR immutability): ECR tags are IMMUTABLE and one shared tag
# (placeholder_image_tag in terraform.tfvars) is used across ALL components. To ship
# a code change: bump placeholder_image_tag in environments/dev/terraform.tfvars,
# run this script (it rebuilds and pushes every component at the new tag), then run
# `terraform apply` (which publishes a new Lambda version and repoints the live alias).
#
# Lambda REJECTS OCI image manifests, so we force the Docker v2 media type
# (--provenance=false, oci-mediatypes=false). Never use `docker buildx imagetools
# create` to copy tags between images: it emits OCI manifests Lambda cannot run.
#
# Prereqs: Docker running; AWS credentials; the ECR repos already created
# (terraform apply, or `terraform -chdir=environments/dev apply -target='module.ecr'`
# on a first-time bootstrap; see docs/BOOTSTRAP.md).
set -euo pipefail
cd "$(dirname "$0")/.."

# Portability guards (this script is meant to run on a successor's fresh machine):
# associative arrays need bash 4+ (macOS ships 3.2 as /bin/bash).
if [ -z "${BASH_VERSINFO:-}" ] || [ "${BASH_VERSINFO[0]}" -lt 4 ]; then
  echo "ERROR: needs bash 4+ (associative arrays). macOS default is 3.2; run with a" >&2
  echo "newer bash, e.g. 'brew install bash' then '/opt/homebrew/bin/bash $0'." >&2
  exit 1
fi
# Prefer python3 (bare 'python' is absent on recent macOS / stock Debian).
PY=$(command -v python3 || command -v python || true)
[ -n "$PY" ] || { echo "ERROR: python3 not found on PATH." >&2; exit 1; }
command -v docker >/dev/null || { echo "ERROR: docker not found on PATH." >&2; exit 1; }

TF="terraform -chdir=environments/dev"
TAG=$(grep -E '^[[:space:]]*placeholder_image_tag' environments/dev/terraform.tfvars | sed -E 's/[^"]*"([^"]+)".*/\1/')
URLS_JSON=$($TF output -json ecr_repository_urls)

# ECR component key -> source directory (the Dockerfile lives in src/<dir>/).
declare -A SRC=(
  [intake]=component_a_intake
  [enrichment]=component_b_enrichment
  [risk_scoring]=component_c_risk_scoring
  [disposition]=component_d_disposition
  [batch_ingest]=component_e_batch_ingest
  [feeder]=component_f_feeder
  [refresher]=component_g_refresher
  [console_api]=console_api
)

# Registry host + region derived from any repo URL (acct.dkr.ecr.region.amazonaws.com/repo).
FIRST_URL=$(echo "$URLS_JSON" | "$PY" -c 'import sys,json;print(next(iter(json.load(sys.stdin).values())))')
REGISTRY=${FIRST_URL%%/*}
REGION=$(echo "$REGISTRY" | cut -d. -f4)

# The default buildx "docker" driver cannot push via --output type=image; ensure a
# docker-container (buildkit) builder that can. Idempotent.
docker buildx use prepayguard 2>/dev/null || \
  docker buildx create --name prepayguard --driver docker-container --use >/dev/null

echo "→ ECR login ($REGISTRY, tag $TAG)"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"

for key in "${!SRC[@]}"; do
  dir=${SRC[$key]}
  url=$(echo "$URLS_JSON" | "$PY" -c "import sys,json;print(json.load(sys.stdin)['$key'])")
  echo "→ build+push $key  (src/$dir)  ->  $url:$TAG"
  docker buildx build \
    --provenance=false \
    --platform linux/amd64 \
    --output "type=image,oci-mediatypes=false,push=true" \
    -t "$url:$TAG" \
    "src/$dir"
done

echo "done. All ${#SRC[@]} images pushed at $TAG."
echo "next: $TF apply   (publishes a new Lambda version + repoints the live alias)"
