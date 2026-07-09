# ERRORS.md — PrePayGuard ("Treasury")
# Post-mortems for real failures (ERR-N entries). Checked by /debug before any
# diagnosis. Empty is a good sign; near-misses live in MEMORY_CORRECTIONS.md
# REFLEXION entries instead.

_v0.1.0 closed without a blocking failure (HashiCorp CDN flakiness and toolchain
gaps were friction, resolved in-session — see the v0.1.0 REFLEXION and PAT-T5/T6/T7)._

---

## ERR-1 - API Gateway model rejects TF schema: `? :` stringifies integer constraints (Phase 2.1e/2.1f)
**Date:** 2026-07-09
**Symptom:** `terraform apply` of the intake payee-validation model (DEC-29) failed:
`UpdateModel ... BadRequestException: Invalid model specified ... [Invalid model schema specified, Invalid model schema specified]`. The Lambda env-var change in the same apply had already succeeded, leaving a partial apply.
**Diagnosis:** the model schema was built as
`payee = var.payee_validation_enabled ? {type,minLength,maxLength,pattern} : {type,minLength}`.
HCL's ternary requires both result values to share a type; the two objects differ in shape, so HCL unified them to `map(string)` and coerced the numeric constraints to **strings** — `jsonencode` then emitted `"maxLength":"35"` / `"minLength":"1"`. JSON Schema requires `maxLength`/`minLength` to be **integers**, so API Gateway rejected the schema. Confirmed by `terraform plan` showing `maxLength = 35 -> "35"`, and by a direct `aws apigateway update-model` succeeding with integer `35` while the TF-rendered string form failed.
**Fix:** select between two independently-`jsonencode`d **strings**, not two objects —
`schema = var.payee_validation_enabled ? local.intake_schema_validated : local.intake_schema_open`,
where each local `jsonencode`s a fully-typed object. Each branch keeps `maxLength` an integer; the ternary now chooses a string, so no type unification occurs. After the fix `terraform apply` is clean and `plan` shows no drift.
**Lesson (PAT candidate):** never put a Terraform `? :` between two objects of different shape if the values must keep distinct types — the unification silently stringifies. Put the conditional at the `jsonencode`-string level. Also: API Gateway `CreateModel` validates lazily but `UpdateModel` validates strictly, so a bad schema can pass initial creation and only fail on a later edit.
**Status:** RESOLVED (v3.9.0).
