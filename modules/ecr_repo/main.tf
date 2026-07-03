# modules/ecr_repo — one private repository per component image (used 4x).
# Immutable tags + scan-on-push are the DEC-8/DEC-9 posture at the registry
# edge; Grype scans the built images in CI (v0.6.0).
#
# NOTE for later gates (recorded from the v0.1.0 grounding review): when
# digest-pinning images, the aws_ecr_image data source does NOT export
# `image_digest` — the manifest digest is its `id` attribute. Use
# `${repository_url}@${data.aws_ecr_image.x.id}` and prefer `code_sha256`
# as the container-image update trigger on aws_lambda_function.

resource "aws_ecr_repository" "this" {
  name                 = var.repo_name
  image_tag_mutability = "IMMUTABLE" # a tag can never be silently repointed — deploys are auditable
  force_delete         = var.force_delete

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS" # AWS-managed KMS key (no CMK cost); satisfies CKV_AWS_136
  }
}

# Keep the registry bounded: expire all but the most recent images.
resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the last ${var.keep_last_images} images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.keep_last_images
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
