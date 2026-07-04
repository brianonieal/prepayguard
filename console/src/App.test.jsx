import { render, screen, fireEvent } from "@testing-library/react";
import App from "./App.jsx";
import { parseCsv } from "./lib/csv.js";
import { canonicalize } from "./lib/integrity.js";
import { explainScore } from "./lib/score.js";

// Keep tests hermetic: mock auth + the signed API (no Amplify / AWS in jsdom).
vi.mock("./lib/auth.js", () => ({
  login: async () => ({ username: "brian@example.test", signInDetails: { loginId: "brian@example.test" } }),
  logout: async () => {},
  currentUser: async () => null, // start logged-out so the login gate shows
  currentGroups: vi.fn(async () => ["admin"]), // default: full-access role
  roleFromGroups: (g) => g.includes("admin") ? "admin" : g.includes("reviewer") ? "reviewer" : g.includes("auditor") ? "auditor" : g.includes("submitter") ? "submitter" : "none",
}));

vi.mock("./lib/api.js", () => {
  const reviews = [
    { payment_id: "console-smoke-1", payee: "Umbrella Holdings Group", match: "name · treasury_offset", score: 48, status: "pending", received_at: "2026-07-03T23:52:41+00:00", audit_id: "a1" },
    { payment_id: "e2e-review-1", payee: "Acme Shell LLC", match: "name · sam_exclusions", score: 60, status: "approved", received_at: "2026-07-03T23:33:00+00:00", audit_id: "a2" },
  ];
  const record = {
    schema_version: "1.0", audit_id: "a1", payment_id: "console-smoke-1", audited_at: "2026-07-03T23:52:41+00:00",
    decision: { disposition: "review", risk_score: 48, reasons: ["name_exact match on treasury_offset (severity medium)"] },
    evidence: { matches: [
      { source: "treasury_offset", matched_on: "name_exact", confidence: 80, severity: "medium" },
      { source: "oig_leie", matched_on: "name_semantic", confidence: 74, severity: "high", similarity: 0.74 },
    ], match_count: 2, highest_confidence: 80 },
    payment: { payee: "Umbrella Holdings Group", amount: 75 },
    provenance: { pipeline: ["intake", "enrichment", "risk_scoring", "disposition"], component_versions: { disposition: "2.1.0" }, reference_list_version: 3 },
    integrity: { algorithm: "sha256", sha256: "deadbeef" },
  };
  return {
    submitPayment: async () => ({ message_id: "m1", idempotent_replay: false }),
    listReviews: async () => ({ reviews, count: reviews.length, next_cursor: null }),
    getAudit: async () => ({ key: "k", record }),
    getBrief: async () => ({ brief: "Flagged on a semantic match to an OIG-excluded entity. Recommend INVESTIGATE.", model: "amazon.nova-lite-v1:0", generated_at: "2026-07-04T18:00:00+00:00" }),
    getAnalytics: async () => ({ total_screened: 12, disposition_mix: { approve: 7, review: 3, reject: 2 }, hit_rate: 41.7, throughput: [{ day: "2026-07-04", count: 12 }], queue: { pending: 3, avg_pending_score: 55, oldest_pending: "2026-07-03" }, reviewer_productivity: [{ reviewer: "kim", decisions: 5 }] }),
    getAuditLog: async () => ({ entries: [{ payment_id: "x4", disposition: "reject", audited_at: "2026-07-04T10:00:00", key: "k" }], count: 1, truncated: false }),
    decide: async () => ({ status: "approved" }),
    listAttachments: async () => ({ attachments: [] }),
    presignAttachment: async () => ({ upload_url: "http://x", key: "k" }),
    uploadFile: async () => {},
    presignBatch: async () => ({ upload_url: "http://x", batch_id: "b1", key: "batch-imports/b1/f.csv" }),
    getBatch: async () => ({ batch_id: "b1", status: "complete", queued: 2, duplicate: 0, rejected: 0, errors: [] }),
    listBatches: async () => ({ batches: [] }),
    bulkDecide: vi.fn(async () => ({ decision: "approved", applied: 1, results: [] })),
    resetData: vi.fn(async () => ({ cleared: { "treasury-dev-reviews": 5, "treasury-dev-audit-index": 5 }, total: 10, note: "immutable S3 audit records (Object Lock) are unaffected" })),
    getReference: async () => ({
      version: 1, updated_at: "2026-07-04T00:00:00+00:00", updated_by: "seed", sources: {},
      entries: [{ name: "Acme Shell LLC", tin: "900000002", source: "sam_exclusions", severity: "high" }],
    }),
    putReference: vi.fn(async () => ({ version: 2, entry_count: 2 })),
    listReferenceVersions: async () => ({ versions: [{ version: 1, published_at: "2026-07-04T00:00:00+00:00", size: 500 }] }),
    getReferenceVersion: async () => ({ version: 1, updated_by: "seed", entries: [] }),
    getShowcase: async () => ({
      summary: { total_screened: 178, disposition_mix: { approve: 136, review: 31, reject: 11 }, hit_rate: 23.6,
        throughput: [{ day: "2026-07-04", count: 42 }], queue: { pending: 31, avg_pending_score: 55, oldest_pending: "2026-07-03" }, reviewer_productivity: [] },
      match_types: { none: 20, tin: 6, name_semantic: 8, name_fuzzy: 4, name_exact: 2 },
      match_sample_size: 40,
      examples: {
        approve: { payment_id: "APP-1", payee: "Clean Vendor LLC", amount: 1200, disposition: "approve", risk_score: 0, reasons: [], matches: [], reference_list_version: 3 },
        review: { payment_id: "REV-1", payee: "Globex Overseas Incorporated", amount: 48000, disposition: "review", risk_score: 60, reasons: ["name_semantic match"], matches: [{ matched_on: "name_semantic", source: "sam_exclusions", severity: "medium", confidence: 86, similarity: 0.857 }], reference_list_version: 3 },
        reject: { payment_id: "REJ-1", payee: "Zeta Shell Holdings LLC", amount: 250000, disposition: "reject", risk_score: 95, reasons: ["tin match"], matches: [{ matched_on: "tin", source: "sam_exclusions", severity: "high", confidence: 95 }], reference_list_version: 3 },
      },
    }),
  };
});

import { bulkDecide, putReference, resetData } from "./lib/api.js";
import { currentGroups } from "./lib/auth.js";

beforeEach(() => { window.location.hash = ""; localStorage.clear(); currentGroups.mockResolvedValue(["admin"]); });

const signIn = async () => {
  await screen.findByText("PrePayGuard payment integrity console");
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "brian@example.test" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw123456789!" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await screen.findByTestId("role-chip");  // role-agnostic: signed in + role resolved
};

// --- pure logic ---
test("canonicalize matches Python sort_keys/compact", () => {
  expect(canonicalize({ b: 1, a: [3, 2], c: "x" })).toBe('{"a":[3,2],"b":1,"c":"x"}');
});
test("explainScore mirrors the engine (name match capped → review)", () => {
  const { best, band } = explainScore({ evidence: { matches: [{ matched_on: "name_exact", source: "sam_exclusions", confidence: 80, severity: "medium" }] } });
  expect(best).toBe(48); expect(band).toBe("review");
});
test("csv parser: valid rows, optional tin, bad rows reported", () => {
  const { rows, errors } = parseCsv("payment_id,payee,payee_tin,amount\nP-1,A,900000001,100\n,NoId,,5");
  expect(rows).toHaveLength(1); expect(rows[0].amount).toBe(100); expect(errors).toHaveLength(1);
});

// --- app / screens (mocked live data) ---
test("login gates the app", async () => {
  render(<App />);
  await signIn();
  expect(screen.getByText("Submit payments for screening")).toBeInTheDocument();
});

test("submit fakes a queued result", async () => {
  render(<App />);
  await signIn();
  fireEvent.change(screen.getByLabelText("Payment ID"), { target: { value: "PAY-1" } });
  fireEvent.change(screen.getByLabelText("Amount (USD)"), { target: { value: "10" } });
  fireEvent.change(screen.getByLabelText("Payee name"), { target: { value: "V" } });
  fireEvent.click(screen.getByRole("button", { name: "Submit for screening" }));
  expect(await screen.findByText(/Queued\./)).toBeInTheDocument();
});

test("review queue lists live items and filters", async () => {
  render(<App />);
  await signIn();
  fireEvent.click(await screen.findByRole("button", { name: "Review Queue" }));
  expect(await screen.findByText("console-smoke-1")).toBeInTheDocument();
  expect(screen.getByText("Umbrella Holdings Group")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Search reviews"), { target: { value: "zzz" } });
  expect(screen.getByText(/No payments match/)).toBeInTheDocument();
});

test("audit detail: evidence, verify button, decision flips status", async () => {
  render(<App />);
  await signIn();
  fireEvent.click(await screen.findByRole("button", { name: "Review Queue" }));
  fireEvent.click(await screen.findByRole("button", { name: "Review →" }));
  expect(await screen.findByText("Screening evidence")).toBeInTheDocument();
  expect(screen.getByText(/name semantic match/)).toBeInTheDocument();  // v2.2.0
  expect(screen.getByText(/similarity 0\.74/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Verify integrity" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Approve payment" }));
  expect(await screen.findByText("approved")).toBeInTheDocument();
});

test("audit detail: AI brief is advisory and shows on demand", async () => {
  render(<App />);
  await signIn();
  fireEvent.click(await screen.findByRole("button", { name: "Review Queue" }));
  fireEvent.click(await screen.findByRole("button", { name: "Review →" }));
  expect(await screen.findByText(/not part of the audit record/)).toBeInTheDocument();  // disclaimer
  fireEvent.click(screen.getByRole("button", { name: "Get AI brief" }));
  expect(await screen.findByText(/Recommend INVESTIGATE/)).toBeInTheDocument();
});

test("deep link routes to a case", async () => {
  window.location.hash = "#/reviews/console-smoke-1";
  render(<App />);
  await screen.findByText("PrePayGuard payment integrity console");
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "b@x.test" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText(/Why score/)).toBeInTheDocument();
});

test("user menu → profile, settings, sign out", async () => {
  render(<App />);
  await signIn();
  fireEvent.click(screen.getByTestId("user-menu-btn"));
  fireEvent.click(screen.getByRole("button", { name: "Profile" }));
  expect(await screen.findByText("Cognito sub")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("user-menu-btn"));
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.getByText("Appearance")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("user-menu-btn"));
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  expect(await screen.findByText("PrePayGuard payment integrity console")).toBeInTheDocument();
});

test("settings density toggle applies and persists", async () => {
  render(<App />);
  await signIn();
  fireEvent.click(screen.getByTestId("user-menu-btn"));
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  fireEvent.click(screen.getByLabelText("Compact"));
  expect(document.querySelector(".app.compact")).toBeTruthy();
  expect(JSON.parse(localStorage.getItem("tc.settings")).density).toBe("compact");
});

test("footer grounds the page", async () => {
  render(<App />);
  await signIn();
  expect(screen.getByText(/immutably audited/)).toBeInTheDocument();
});

test("batch upload parses rows then ingests server-side and shows a summary", async () => {
  render(<App />);
  await signIn();
  const file = new File(["payment_id,payee,amount\nB-1,Batch Vendor,25\nB-2,Other,50"], "batch.csv", { type: "text/csv" });
  fireEvent.change(screen.getByTestId("csv-input"), { target: { files: [file] } });
  expect(await screen.findByText("B-1")).toBeInTheDocument();
  // Server-side ingestion (v1.6.0): one upload → poll the batch summary.
  fireEvent.click(await screen.findByRole("button", { name: "Submit 2 payments" }));
  expect(await screen.findByText(/Batch ingested/)).toBeInTheDocument();
  expect(screen.getByText(/2 queued for screening/)).toBeInTheDocument();
});

test("batch upload accepts a JSON file and previews rows client-side", async () => {
  render(<App />);
  await signIn();
  const file = new File([JSON.stringify([{ payment_id: "J-1", payee: "Beta Vendor", amount: 25 }])],
    "vendors.json", { type: "application/json" });
  fireEvent.change(screen.getByTestId("csv-input"), { target: { files: [file] } });
  expect(await screen.findByText("J-1")).toBeInTheDocument();
  expect(screen.getByText("Beta Vendor")).toBeInTheDocument();
});

test("batch upload accepts an Excel file (server-parsed, no client preview)", async () => {
  render(<App />);
  await signIn();
  const file = new File([new Uint8Array([1, 2, 3])], "payroll.xlsx",
    { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  fireEvent.change(screen.getByTestId("csv-input"), { target: { files: [file] } });
  expect(await screen.findByText(/parsed server-side on upload/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Upload payroll\.xlsx/ })).toBeInTheDocument();
});

test("admin sees the Analytics tab and dashboard", async () => {
  render(<App />);
  await signIn();
  fireEvent.click(await screen.findByRole("button", { name: "Analytics" }));
  expect(await screen.findByText("Total screened")).toBeInTheDocument();
  expect(screen.getByText("Hit rate")).toBeInTheDocument();
  expect(screen.getByText("Disposition mix")).toBeInTheDocument();
});

test("auditor role: analytics visible, review queue is read-only (no decide)", async () => {
  currentGroups.mockResolvedValue(["auditor"]);
  render(<App />);
  await signIn();
  expect(await screen.findByRole("button", { name: "Analytics" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Submit Payment" })).toBeNull();   // auditor can't submit
  fireEvent.click(screen.getByRole("button", { name: "Review Queue" }));
  fireEvent.click((await screen.findAllByRole("button", { name: "View →" }))[0]); // "View", not "Review"
  expect(await screen.findByText("Screening evidence")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Approve payment" })).toBeNull();   // no decide controls
});

test("reviewer role has no Analytics tab", async () => {
  currentGroups.mockResolvedValue(["reviewer"]);
  render(<App />);
  await signIn();
  expect(await screen.findByRole("button", { name: "Review Queue" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Analytics" })).toBeNull();
});

test("submitter role sees Submit but not the Review Queue", async () => {
  currentGroups.mockResolvedValue(["submitter"]);
  render(<App />);
  await signIn();
  expect(await screen.findByTestId("role-chip")).toHaveTextContent("submitter");
  expect(screen.getByRole("button", { name: "Submit Payment" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Review Queue" })).toBeNull();
});

test("admin role sees both tabs and the role chip", async () => {
  render(<App />);
  await signIn();
  expect(await screen.findByRole("button", { name: "Review Queue" })).toBeInTheDocument();
  expect(screen.getByTestId("role-chip")).toHaveTextContent("admin");
});

test("admin edits the reference list and publishes a new version", async () => {
  render(<App />);
  await signIn();
  fireEvent.click(await screen.findByRole("button", { name: "Reference Data" }));
  expect(await screen.findByText("Reference data")).toBeInTheDocument();
  expect((await screen.findAllByText("v1")).length).toBeGreaterThan(0); // stat card + history pill
  // Edit an entry name -> the working copy is dirty -> publish becomes available.
  fireEvent.change(screen.getByLabelText("entry 0 name"), { target: { value: "Acme Shell Holdings LLC" } });
  fireEvent.click(screen.getByRole("button", { name: /Publish new version/ }));
  expect(await screen.findByText(/Published version 2/)).toBeInTheDocument();
  expect(putReference).toHaveBeenCalledWith(expect.objectContaining({
    entries: [expect.objectContaining({ name: "Acme Shell Holdings LLC" })],
  }));
});

test("reviewer role has no Reference Data tab", async () => {
  currentGroups.mockResolvedValue(["reviewer"]);
  render(<App />);
  await signIn();
  expect(await screen.findByRole("button", { name: "Review Queue" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Reference Data" })).toBeNull();
});

test("audit detail cites the reference list version", async () => {
  render(<App />);
  await signIn();
  fireEvent.click(await screen.findByRole("button", { name: "Review Queue" }));
  fireEvent.click(await screen.findByRole("button", { name: "Review →" }));
  expect(await screen.findByText(/v3 \(list version screened against\)/)).toBeInTheDocument();
});

test("Overview showcase renders the live story, charts and worked examples", async () => {
  render(<App />);
  await signIn();
  fireEvent.click(await screen.findByRole("button", { name: "Overview" }));
  expect(await screen.findByText(/payments screened/)).toBeInTheDocument();       // hero live stat
  expect(screen.getByText("How a payment moves through the pipeline")).toBeInTheDocument();
  expect(screen.getByText("Three real decisions")).toBeInTheDocument();
  expect(screen.getByText("Globex Overseas Incorporated")).toBeInTheDocument();   // review example
  expect(screen.getByText("Zeta Shell Holdings LLC")).toBeInTheDocument();        // reject example
});

test("submitter role does not see the Overview tab", async () => {
  currentGroups.mockResolvedValue(["submitter"]);
  render(<App />);
  await signIn();
  expect(await screen.findByRole("button", { name: "Submit Payment" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Overview" })).toBeNull();
});

test("admin sees Demo controls; typing RESET enables Clear data and runs the reset", async () => {
  render(<App />);
  await signIn();
  fireEvent.click(screen.getByTestId("user-menu-btn"));
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.getByText("Demo controls")).toBeInTheDocument();
  const btn = screen.getByRole("button", { name: "Clear data" });
  expect(btn).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Reset confirmation"), { target: { value: "RESET" } });
  expect(btn).toBeEnabled();
  fireEvent.click(btn);
  expect(await screen.findByTestId("reset-result")).toBeInTheDocument();
  expect(resetData).toHaveBeenCalled();
});

test("reviewer does not see Demo controls in Settings", async () => {
  currentGroups.mockResolvedValue(["reviewer"]);
  render(<App />);
  await signIn();
  fireEvent.click(screen.getByTestId("user-menu-btn"));
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.getByText("Appearance")).toBeInTheDocument();
  expect(screen.queryByText("Demo controls")).toBeNull();
});

test("review queue multi-select applies a bulk decision", async () => {
  render(<App />);
  await signIn();
  fireEvent.click(await screen.findByRole("button", { name: "Review Queue" }));
  fireEvent.click(await screen.findByLabelText("Select console-smoke-1"));
  expect(screen.getByText(/selected/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Approve 1" }));
  expect(bulkDecide).toHaveBeenCalledWith(["console-smoke-1"], "approved");
});
