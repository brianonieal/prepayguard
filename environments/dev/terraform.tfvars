aws_region = "us-east-2"

# ============================================================================
# AUDIT RETENTION — READ BEFORE CHANGING (DEC-4 irreversibility)
# COMPLIANCE-mode retention cannot be shortened or removed on any written
# object, by any principal, including account root. AWS Support cannot
# override it.
#
# dev uses ONE DAY so experiments never strand objects longer than 24h.
# The real retention for demo/graded writes is a deliberate sign-off decision
# scheduled BEFORE the v0.4.0 apply (Component D, first audit writes). When
# choosing it, also choose the UNIT deliberately: days and years produce
# different retain-until dates (2555 days != 7 calendar years).
# ============================================================================
audit_retention_days = 1

placeholder_image_tag = "v2.1.2" # current deployed image tag (immutable tags; bump per release — DEC-10 publishes a new version + repoints the alias)
