# CONTRACT.md
# Stable project identity. Locked under BUILD APPROVED.

## PROJECT
- **Name:** PrePayGuard
- **External name / codename:** "Treasury"
- **Owner:** Brian Onieal (brian.onieal@gmail.com)
- **Course:** JHU Certificate in AI Engineering — CO.EN.AIE.LLL.2026.01 (capstone)
- **PROJECT_TYPE:** personal
- **BUILD_TYPE:** internal / capstone deliverable (graded, delivered to course instructors; not public GA, not sold)
- **Created:** 2026-07-03

## WHAT IT IS
Cloud-native pre-payment integrity screening pipeline modeled on the U.S. Treasury
Bureau of the Fiscal Service **Do Not Pay** program. Screens payments before
disbursement: clean payments auto-approve, ambiguous route to human review, bad
payments are rejected. Faithful implementation of a proven government reference
pattern, not a novel concept.

## STACK (LOCKED — see TREASURY_DECISIONS_LOG.md)
- **Cloud:** AWS only — API Gateway, Lambda (container images), SQS, S3 (Object Lock), ECR, Secrets Manager, CloudWatch
- **IaC:** Terraform (shared-module pattern, DEC-1)
- **App code:** Python (all four Lambda handlers)
- **CI/CD:** GitHub Actions (plan-only on PRs, no auto-apply — DEC-6)
- **Security tooling:** pip-audit, Grype, tflint, checkov, ruff (DEC-8, DEC-9)

## ARCHITECTURE (4 components, SQS-decoupled)
- **A. Payment Intake API** — API Gateway (AWS_IAM auth, DEC-5) → Lambda container. Idempotency check (commitment 1) → output SQS. Module: `api_intake_stage`.
- **B. Enrichment & Reference-Match** — SQS-triggered Lambda container. Module: `queue_worker_stage` (shared).
- **C. Risk-Scoring & Decision Engine** — SQS-triggered Lambda container. Module: `queue_worker_stage` (shared).
- **D. Disposition Router & Audit Logger** — SQS-triggered Lambda container. Writes immutable audit record to S3 Object Lock (commitment 4), routes ambiguous → review queue (commitment 2), posts webhook via Secrets Manager (DEC-7). Module: `queue_worker_stage` (shared, secrets_arn set).

## FOUR GRADED COMMITMENTS (evidence required, not prose)
1. Idempotency via payment-ID deduplication — `tests/test_idempotency.py`
2. Component-failure routing to manual review — `tests/test_failure_routing.py`
3. Queue-depth scaling — `tests/test_queue_depth_scaling.py`
4. S3 Object Lock immutability — `tests/test_object_lock.py`
(+ DEC-7 review-notification evidence — `tests/test_review_notification.py`)

## BANNED / EXCLUDED
- **No frontend** — backend-only pipeline. MOCKUPS APPROVED and FRONTEND APPROVED are **N/A for every gate**. No MOCKUPS.md, FRONTEND_SPEC.md, or COMPONENT_REGISTRY.md.
- **No EC2 workers; no zip-based Lambda** (DEC-2 — container images only).
- **No QLDB** (retired 2025-07-31; DEC-4 uses S3 Object Lock instead).
- **No API-key-only auth on Component A** (DEC-5 requires AWS_IAM).
- **No auto-apply on merge** (DEC-6 — apply stays manual).
- **No cross-project stacks** — Supabase, Vercel, Render, SQLAlchemy, and any other pattern from Brian's unrelated projects do **not** apply here.

## CLIENT BILLING
N/A — personal academic project. No freelance-billing, no TIMELOG dollar tracking,
no client status emails. Hour logging for Brian's own record is fine.

## DECISIONS
All 12 architectural/process decisions are LOCKED. See `DECISIONS.md` (seeded verbatim
from `TREASURY_DECISIONS_LOG.md` at foundation build). Do not re-open a LOCKED decision
without a stated reason to pivot.
