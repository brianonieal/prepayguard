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
    provenance: { pipeline: ["intake", "enrichment", "risk_scoring", "disposition"], component_versions: { disposition: "1.4.1" } },
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
  };
});

beforeEach(() => { window.location.hash = ""; localStorage.clear(); });

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
  fireEvent.click(screen.getByRole("button", { name: "Review Queue" }));
  expect(await screen.findByText("console-smoke-1")).toBeInTheDocument();
  expect(screen.getByText("Umbrella Holdings Group")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Search reviews"), { target: { value: "zzz" } });
  expect(screen.getByText(/No payments match/)).toBeInTheDocument();
});

test("audit detail: evidence, verify button, decision flips status", async () => {
  render(<App />);
  await signIn();
  fireEvent.click(screen.getByRole("button", { name: "Review Queue" }));
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

test("batch upload stages parsed rows", async () => {
  render(<App />);
  await signIn();
  const file = new File(["payment_id,payee,amount\nB-1,Batch Vendor,25"], "batch.csv", { type: "text/csv" });
  fireEvent.change(screen.getByTestId("csv-input"), { target: { files: [file] } });
  expect(await screen.findByText("B-1")).toBeInTheDocument();
  expect(screen.getByText("staged")).toBeInTheDocument();
});
