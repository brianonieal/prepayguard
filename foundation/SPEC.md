# SPEC.md
# Current-gate detail.

## PROJECT COMPLETE — v1.0.0 (2026-07-03)
All 7 gates closed (v0.1.0 → v1.0.0). **All four graded commitments demonstrated by
both automated tests (29/29) and a live end-to-end run on real AWS.** CI green.
14 decisions locked. DEC-11 handoff package delivered: `docs/HANDOFF.md` + `.docx`.

- **Deployed & running** in us-east-2:
  `POST https://0uhsehplg4.execute-api.us-east-2.amazonaws.com/dev/payments` (SigV4).
- Evidence: `docs/evidence/live_e2e_run.txt`, `docs/evidence/live_object_lock_proof.txt`.

## OPEN ITEM (post-completion)
**Teardown** — offer to `terraform destroy` the tear-downable resources to stop the
meter, leaving only `module.audit_store` (its Object Lock objects can't be deleted
until retention expires — DEC-4, by design). Awaiting Brian's go.

## DECISIONS SNAPSHOT
14 of 14 LOCKED.
