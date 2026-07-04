import { render, screen, fireEvent } from "@testing-library/react";
import App from "./App.jsx";

beforeEach(() => { window.location.hash = ""; localStorage.clear(); });

const signIn = () => {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "b@x.test" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw123456789!" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
};

test("login screen renders and gates the app", () => {
  render(<App />);
  expect(screen.getByText("PrePayGuard payment integrity console")).toBeInTheDocument();
  signIn();
  expect(screen.getByText("Submit payments for screening")).toBeInTheDocument();
});

test("submit form fakes a queued result", () => {
  render(<App />);
  signIn();
  fireEvent.change(screen.getByLabelText("Payment ID"), { target: { value: "PAY-1" } });
  fireEvent.change(screen.getByLabelText("Amount (USD)"), { target: { value: "10" } });
  fireEvent.change(screen.getByLabelText("Payee name"), { target: { value: "V" } });
  fireEvent.click(screen.getByRole("button", { name: "Submit for screening" }));
  expect(screen.getByText(/Queued\./)).toBeInTheDocument();
});

test("review queue lists pending items and filters", () => {
  render(<App />);
  signIn();
  fireEvent.click(screen.getByRole("button", { name: /Review Queue/ }));
  expect(screen.getByText("console-smoke-1")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Approved \(1\)/ }));
  expect(screen.getByText("e2e-review-1")).toBeInTheDocument();
});

import { parseCsv } from "./lib/csv.js";
import { canonicalize } from "./lib/integrity.js";
import { explainScore } from "./lib/score.js";

test("canonicalize matches Python sort_keys/compact output", () => {
  expect(canonicalize({ b: 1, a: [3, 2], c: "x" })).toBe('{"a":[3,2],"b":1,"c":"x"}');
  expect(canonicalize({ z: { y: 1, x: 2 } })).toBe('{"z":{"x":2,"y":1}}');
});

test("explainScore mirrors the engine: name match capped, review band", () => {
  const { best, band, steps } = explainScore({
    evidence: { matches: [{ matched_on: "name_exact", source: "sam_exclusions", confidence: 80, severity: "medium" }] },
  });
  expect(best).toBe(48); // 80 * 0.6
  expect(band).toBe("review");
  expect(steps[0].value).toBe(48);
});

test("deep link routes straight to a case", () => {
  window.location.hash = "#/reviews/console-smoke-1";
  render(<App />);
  signIn();
  expect(screen.getByText(/Why score/)).toBeInTheDocument();
  window.location.hash = "";
});

test("user menu opens profile, settings, and signs out", () => {
  render(<App />);
  signIn();
  fireEvent.click(screen.getByTestId("user-menu-btn"));
  fireEvent.click(screen.getByRole("button", { name: "Profile" }));
  expect(screen.getByText("Cognito sub")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("user-menu-btn"));
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  expect(screen.getByText("Appearance")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("user-menu-btn"));
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  expect(screen.getByText("PrePayGuard payment integrity console")).toBeInTheDocument();
});

test("settings density toggle applies and persists", () => {
  render(<App />);
  signIn();
  fireEvent.click(screen.getByTestId("user-menu-btn"));
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  fireEvent.click(screen.getByLabelText("Compact"));
  expect(document.querySelector(".app.compact")).toBeTruthy();
  expect(JSON.parse(localStorage.getItem("tc.settings")).density).toBe("compact");
});

test("footer grounds the page", () => {
  render(<App />);
  signIn();
  expect(screen.getByText(/immutably audited/)).toBeInTheDocument();
});

test("review queue search filters rows", () => {
  window.location.hash = "";
  render(<App />);
  signIn();
  fireEvent.click(screen.getByRole("button", { name: /Review Queue/ }));
  fireEvent.change(screen.getByLabelText("Search reviews"), { target: { value: "umbrella" } });
  expect(screen.getByText("console-smoke-1")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Search reviews"), { target: { value: "zzz-none" } });
  expect(screen.getByText(/No payments match/)).toBeInTheDocument();
});

test("csv parser: valid rows, optional tin, bad rows reported", () => {
  const { rows, errors } = parseCsv(
    "payment_id,payee,payee_tin,amount\nP-1,Vendor A,900000001,100\nP-2,Vendor B,,50\n,MissingId,,10\nP-4,Bad Amount,,abc",
  );
  expect(rows).toHaveLength(2);
  expect(rows[0]).toMatchObject({ payment_id: "P-1", payee_tin: "900000001", amount: 100 });
  expect(rows[1].payee_tin).toBe("");
  expect(errors).toHaveLength(2);
});

test("batch upload stages parsed rows and submits them", async () => {
  render(<App />);
  signIn();
  const file = new File(["payment_id,payee,amount\nB-1,Batch Vendor,25"], "batch.csv", { type: "text/csv" });
  fireEvent.change(screen.getByTestId("csv-input"), { target: { files: [file] } });
  expect(await screen.findByText("B-1")).toBeInTheDocument();
  expect(screen.getByText("staged")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Submit 1 payment/ }));
  expect(screen.getByText("queued")).toBeInTheDocument();
});

test("audit detail lists case documents and attaches a new one", () => {
  render(<App />);
  signIn();
  fireEvent.click(screen.getByRole("button", { name: /Review Queue/ }));
  fireEvent.click(screen.getByRole("button", { name: "Review →" }));
  expect(screen.getByText("debt-satisfaction-letter.pdf")).toBeInTheDocument();
  const file = new File(["x"], "case-note.pdf", { type: "application/pdf" });
  fireEvent.change(screen.getByTestId("attach-input"), { target: { files: [file] } });
  expect(screen.getByText("case-note.pdf")).toBeInTheDocument();
});

test("review queue shows stat cards", () => {
  render(<App />);
  signIn();
  fireEvent.click(screen.getByRole("button", { name: /Review Queue/ }));
  expect(screen.getByText("Pending review")).toBeInTheDocument();
  expect(screen.getByText("Avg risk score (pending)")).toBeInTheDocument();
});

test("audit detail shows evidence, verify button, and decision flips status", () => {
  render(<App />);
  signIn();
  fireEvent.click(screen.getByRole("button", { name: /Review Queue/ }));
  fireEvent.click(screen.getByRole("button", { name: "Review →" }));
  expect(screen.getByText("Screening evidence")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Verify integrity" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Approve payment" }));
  expect(screen.getByText("approved")).toBeInTheDocument();
});
