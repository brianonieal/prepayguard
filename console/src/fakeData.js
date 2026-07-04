// Static-gate fake data (v1.3.0). Shapes mirror the real console API responses
// exactly, so v1.4.0 wiring swaps the source, not the components.
export const FAKE_REVIEWS = [
  {
    payment_id: "console-smoke-1",
    payee: "Umbrella Holdings Group",
    match: "name · treasury_offset",
    score: 48,
    received_at: "2026-07-03T23:52:41+00:00",
    status: "pending",
    audit_id: "277248ad-ba26-42de-8305-d0994a50339e",
  },
  {
    payment_id: "e2e-review-1",
    payee: "Acme Shell LLC",
    match: "name · sam_exclusions",
    score: 60,
    received_at: "2026-07-03T23:33:27+00:00",
    status: "approved",
    audit_id: "719b2290-d57b-4c8f-9b0f-0d343ffd8ae1",
  },
  {
    payment_id: "PAY-2026-0298",
    payee: "Globex Offshore Inc",
    match: "fuzzy · oig_leie",
    score: 54,
    received_at: "2026-07-01T14:10:00+00:00",
    status: "rejected",
    audit_id: "8c1d3aa0-1111-4222-8333-944445555666",
  },
];

export const FAKE_AUDIT = {
  schema_version: "1.0",
  audit_id: "277248ad-ba26-42de-8305-d0994a50339e",
  payment_id: "console-smoke-1",
  audited_at: "2026-07-03T23:52:41+00:00",
  decision: {
    disposition: "review",
    risk_score: 48,
    reasons: ["name_exact match on treasury_offset (severity medium)"],
  },
  evidence: {
    matches: [
      { source: "treasury_offset", matched_on: "name_exact", confidence: 80, severity: "medium" },
    ],
    match_count: 1,
    highest_confidence: 80,
  },
  payment: { payee: "Umbrella Holdings Group", amount: 75.0 },
  provenance: {
    pipeline: ["intake", "enrichment", "risk_scoring", "disposition"],
    component_versions: { disposition: "1.1.0" },
  },
  integrity: {
    algorithm: "sha256",
    sha256: "9a923f0f7838ed8a41c02be1c55a6c3f8f0d9e2b7a4416c8d92e01aa34bb5cd7",
  },
};
