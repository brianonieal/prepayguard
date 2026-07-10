import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

// A review/reject-shaped record with an INDIVIDUAL payee and no payee_tin.
const REC = {
  payment_id: "P-IND-1",
  audited_at: "2026-07-10T12:00:00+00:00",
  decision: { disposition: "review", risk_score: 60, reasons: ["name_exact match on sam_exclusions (severity high)"] },
  evidence: { matches: [{ source: "sam_exclusions", matched_on: "name_exact", confidence: 80, severity: "high" }], match_count: 1, highest_confidence: 80 },
  payment: { payee: "James O. Wilson Jr.", amount: 4200.5 }, // individual; note: NO payee_tin
  provenance: { reference_list_version: 4, pipeline: ["intake", "enrichment"], component_versions: { disposition: "2.1.0" } },
  integrity: { algorithm: "sha256", sha256: "abc123deadbeefhash" },
};

vi.mock("../lib/api.js", () => ({
  getAudit: vi.fn(async () => ({ key: "k", record: REC })),
  // pii's useNameMasker loads the reference map; list the individual as such.
  getReference: vi.fn(async () => ({
    entries: [{ name: "James O. Wilson Jr.", tin: "", source: "sam_exclusions", severity: "high", classification: "Individual" }],
  })),
}));

import RecordDetail from "./RecordDetail.jsx";

describe("RecordDetail — display-only from the audit record", () => {
  test("renders recorded values verbatim; individual payee masked; TIN not recorded; hash read not recomputed", async () => {
    render(<RecordDetail paymentId="P-IND-1" />);

    // Payee masked to "First L." — full surname must NOT appear anywhere.
    expect(await screen.findByText("James W.")).toBeInTheDocument();
    expect(screen.queryByText(/Wilson/)).toBeNull();

    // Amount currency-formatted from the record (payment.amount = 4200.5).
    expect(screen.getByText("$4,200.50")).toBeInTheDocument();

    // Watchlist version, score, reason, match — all straight from the record.
    expect(screen.getByText("v4")).toBeInTheDocument();
    expect(screen.getByText("60")).toBeInTheDocument();
    expect(screen.getByText(/name_exact match on sam_exclusions/)).toBeInTheDocument();

    // payee_tin is absent → "not recorded", never fabricated.
    expect(screen.getAllByText("not recorded").length).toBeGreaterThan(0);

    // Integrity hash shown verbatim and labeled as read, not recomputed.
    expect(screen.getByText("abc123deadbeefhash")).toBeInTheDocument();
    expect(screen.getByText(/not recomputed/i)).toBeInTheDocument();
  });

  test("approve record with empty matches shows 'No match found'", async () => {
    const { getAudit } = await import("../lib/api.js");
    getAudit.mockResolvedValueOnce({ record: {
      payment_id: "P-APP-1", audited_at: "2026-07-10T13:00:00+00:00",
      decision: { disposition: "approve", risk_score: 0, reasons: ["no reference-source matches"] },
      evidence: { matches: [], match_count: 0, highest_confidence: 0 },
      payment: { payee: "LOCKHEED MARTIN CORP", amount: 15555973334.93 },
      provenance: { reference_list_version: 4 }, integrity: { algorithm: "sha256", sha256: "feedface" },
    } });
    render(<RecordDetail paymentId="P-APP-1" />);
    expect(await screen.findByText("No match found")).toBeInTheDocument();
    expect(screen.getByText("LOCKHEED MARTIN CORP")).toBeInTheDocument(); // entity → full
    expect(screen.getByText("$15,555,973,334.93")).toBeInTheDocument();
  });
});
