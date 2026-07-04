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
  roleFromGroups: (g) => g.includes("admin") ? "admin" : g.includes("reviewer") ? "reviewer" : g.includes("submitter") ? "submitter" : "none",
}));

vi.mock("./lib/api.js", () => {
  const reviews = [
    { payment_id: "console-smoke-1", payee: "Umbrella Holdings Group", match: "name · treasury_offset", score: 48, status: "pending", received_at: "2026-07-03T23:52:41+00:00", audit_id: "a1" },
    { payment_id: "e2e-review-1", payee: "Acme Shell LLC", match: "name · sam_exclusions", score: 60, status: "approved", received_at: "2026-07-03T23:33:00+00:00", audit_id: "a2" },
  ];
  const record = {
    schema_version: "1.0", audit_id: "a1", payment_id: "console-smoke-1", audited_at: "2026-07-03T23:52:41+00:00",
    decision: { disposition: "review", risk_score: 48, reasons: ["name_exact match on treasury_offset (severity medium)"] },
    evidence: { matches: [{ source: "treasury_offset", matched_on: "name_exact", confidence: 80, severity: "medium" }], match_count: 1, highest_confidence: 80 },
    payment: { payee: "Umbrella Holdings Group", amount: 75 },
    provenance: { pipeline: ["intake", "enrichment", "risk_scoring", "disposition"], component_versions: { disposition: "2.1.0" }, reference_list_version: 3 },
    integrity: { algorithm: "sha256", sha256: "deadbeef" },
  };
  return {
    submitPayment: async () => ({ message_id: "m1", idempotent_replay: false }),
    listReviews: async () => ({ reviews, count: reviews.length, next_cursor: null }),
    getAudit: async () => ({ key: "k", record }),
    decide: async () => ({ status: "approved" }),
    listAttachments: async () => ({ attachments: [] }),
    presignAttachment: async () => ({ upload_url: "http://x", key: "k" }),
    uploadFile: async () => {},
    presignBatch: async () => ({ upload_url: "http://x", batch_id: "b1", key: "batch-imports/b1/f.csv" }),
    getBatch: async () => ({ batch_id: "b1", status: "complete", queued: 2, duplicate: 0, rejected: 0, errors: [] }),
    listBatches: async () => ({ batches: [] }),
    bulkDecide: vi.fn(async () => ({ decision: "approved", applied: 1, results: [] })),
    getReference: async () => ({
      version: 1, updated_at: "2026-07-04T00:00:00+00:00", updated_by: "seed", sources: {},
      entries: [{ name: "Acme Shell LLC", tin: "900000002", source: "sam_exclusions", severity: "high" }],
    }),
    putReference: vi.fn(async () => ({ version: 2, entry_count: 2 })),
    listReferenceVersions: async () => ({ versions: [{ version: 1, published_at: "2026-07-04T00:00:00+00:00", size: 500 }] }),
    getReferenceVersion: async () => ({ version: 1, updated_by: "seed", entries: [] }),
  };
});

import { bulkDecide, putReference } from "./lib/api.js";
import { currentGroups } from "./lib/auth.js";

beforeEach(() => { window.location.hash = ""; localStorage.clear(); currentGroups.mockResolvedValue(["admin"]); });

const signIn = async () => {
  await screen.findByText("PrePayGuard payment integrity console");
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "brian@example.test" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw123456789!" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await screen.findByText("Submit payments for screening");
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
  expect(screen.getByRole("button", { name: "Verify integrity" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Approve payment" }));
  expect(await screen.findByText("approved")).toBeInTheDocument();
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

test("review queue multi-select applies a bulk decision", async () => {
  render(<App />);
  await signIn();
  fireEvent.click(await screen.findByRole("button", { name: "Review Queue" }));
  fireEvent.click(await screen.findByLabelText("Select console-smoke-1"));
  expect(screen.getByText(/selected/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Approve 1" }));
  expect(bulkDecide).toHaveBeenCalledWith(["console-smoke-1"], "approved");
});
