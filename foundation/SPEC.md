# SPEC.md
# Current-gate detail. Updated each gate.

## LAST CLOSED: v0.4.0 — Component D (Disposition, Audit, Notify)
**Status:** CLOSED (tagged). pytest 26/26 · LIVE Object-Lock proof PASS ·
fmt/validate clean · tflint/checkov 271/0 (no `.tf` change) · plan 68/0/0.

- **Commitment 4 (live-verified):** D writes an immutable, integrity-hashed
  audit record to the S3 Object Lock bucket; a real delete + shorten-retention
  were both refused (`AccessDenied`) — `docs/evidence/live_object_lock_proof.txt`.
- **Commitment 2:** `review` dispositions routed to the human-review queue;
  processing failures → batch-item-failure → redrive/DLQ.
- **DEC-7:** webhook posted on review, URL from Secrets Manager (least-priv).
- **Deployed:** `module.audit_store` live (9 resources; first real AWS spend).

## NEXT GATE: v0.5.0 — Queue-Depth Scaling & DLQ Hardening
Demonstrate **commitment 3**: event-source-mapping concurrency/batch scaling
under queue depth, CloudWatch queue-depth alarms, DLQ + redrive across stages.
`tests/test_queue_depth_scaling.py`. Opens on **GO**.

## PIPELINE STATUS
All four components have handler logic + passing tests. Three of four graded
commitments demonstrated (1 idempotency, 2 failure routing, 4 immutability);
commitment 3 (scaling) is v0.5.0. First live apply done (audit_store only);
full deploy (4 container images + apply) remains.

## DECISIONS SNAPSHOT
14 of 14 LOCKED. No open questions.
