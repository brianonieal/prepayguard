// Batch payment CSV parser (client-side by design: rows are submitted
// one-by-one to the idempotent intake API, so batch retries are safe).
// Expected header: payment_id,payee,payee_tin,amount  (payee_tin optional)
export function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length === 0) return { rows: [], errors: ["file is empty"] };

  const header = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const idx = {
    payment_id: header.indexOf("payment_id"),
    payee: header.indexOf("payee"),
    payee_tin: header.indexOf("payee_tin"),
    amount: header.indexOf("amount"),
  };
  if (idx.payment_id === -1 || idx.payee === -1 || idx.amount === -1) {
    return { rows: [], errors: ["header must include payment_id, payee, amount (payee_tin optional)"] };
  }

  const rows = [];
  const errors = [];
  lines.slice(1).forEach((line, i) => {
    const cells = line.split(",").map((c) => c.trim());
    const row = {
      payment_id: cells[idx.payment_id] || "",
      payee: cells[idx.payee] || "",
      payee_tin: idx.payee_tin >= 0 ? cells[idx.payee_tin] || "" : "",
      amount: Number(cells[idx.amount]),
    };
    if (!row.payment_id || !row.payee) errors.push(`row ${i + 2}: payment_id and payee are required`);
    else if (!Number.isFinite(row.amount) || row.amount < 0) errors.push(`row ${i + 2}: invalid amount`);
    else rows.push(row);
  });
  return { rows, errors };
}

// v2.1.2: JSON batch parser, mirroring Component E's contract. Accepts a
// top-level array of payment objects, or { "payments": [...] }.
export function parseJsonPayments(text) {
  let data;
  try { data = JSON.parse(text); }
  catch (e) { return { rows: [], errors: ["invalid JSON: " + (e.message || e)] }; }
  if (data && !Array.isArray(data) && Array.isArray(data.payments)) data = data.payments;
  if (!Array.isArray(data)) return { rows: [], errors: ['JSON must be an array of payment objects (or {"payments": [...]})'] };

  const rows = [];
  const errors = [];
  data.forEach((o, i) => {
    const n = i + 1;
    if (!o || typeof o !== "object") { errors.push(`item ${n}: must be an object`); return; }
    const payment_id = String(o.payment_id ?? "").trim();
    const payee = String(o.payee ?? "").trim();
    const amount = Number(o.amount);
    if (!payment_id || !payee) errors.push(`item ${n}: payment_id and payee are required`);
    else if (!Number.isFinite(amount) || amount < 0) errors.push(`item ${n}: invalid amount`);
    else rows.push({ payment_id, payee, payee_tin: o.payee_tin ? String(o.payee_tin).trim() : "", amount });
  });
  return { rows, errors };
}

// Robust CSV parse (handles quoted fields with commas/newlines) -> array of arrays.
// The naive split above is fine for the simple payments format; the raw USAspending
// Custom Award Data file has 297 quoted columns and needs this.
function csvRows(text) {
  const rows = []; let row = [], field = "", inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else inQ = false; }
      else field += c;
    } else if (c === '"') inQ = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else if (c !== "\r") field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  return rows.filter((r) => r.some((f) => f.trim() !== ""));
}
const firstCol = (header, names) => { for (const n of names) { const i = header.indexOf(n); if (i >= 0) return i; } return -1; };

// v3.9: Feed-page upload. Accepts a plain payments file (payment_id, payee, amount)
// OR a raw USAspending Custom Award Data CSV (recipient_name + award id + amount, real
// column names verified against a live download), normalizing both to payment rows for
// screening. Returns { kind: "payments" | "award" | null, rows, errors }.
export function parseFeedUpload(text, ext) {
  if (ext === "json") { const r = parseJsonPayments(text); return { kind: r.rows.length ? "payments" : null, rows: r.rows, errors: r.errors }; }
  const rows = csvRows(text);
  if (!rows.length) return { kind: null, rows: [], errors: ["file is empty"] };
  const header = rows[0].map((h) => h.trim().toLowerCase());
  const body = rows.slice(1);
  // plain payments file
  const pi = header.indexOf("payment_id"), py = header.indexOf("payee"), am = header.indexOf("amount");
  if (pi >= 0 && py >= 0 && am >= 0) {
    const out = [], errors = [];
    body.forEach((c, i) => {
      const payment_id = (c[pi] || "").trim(), payee = (c[py] || "").trim(), amount = Number(c[am]);
      if (!payment_id || !payee) errors.push(`row ${i + 2}: payment_id and payee are required`);
      else if (!Number.isFinite(amount) || amount < 0) errors.push(`row ${i + 2}: invalid amount`);
      else out.push({ payment_id, payee, amount });
    });
    return { kind: "payments", rows: out, errors };
  }
  // raw USAspending Custom Award Data CSV -> map recipient/id/amount to payment rows
  const rn = header.indexOf("recipient_name");
  const idc = firstCol(header, ["contract_award_unique_key", "assistance_award_unique_key", "award_id_piid", "award_id_fain"]);
  const amc = firstCol(header, ["current_total_value_of_award", "total_obligated_amount", "total_dollars_obligated", "federal_action_obligation"]);
  if (rn >= 0 && amc >= 0) {
    const out = [], seen = new Set();
    body.forEach((c, i) => {
      const payee = (c[rn] || "").trim();
      const amount = Number(c[amc]);
      const id = (idc >= 0 && (c[idc] || "").trim()) || `ROW${i + 1}`;
      if (!payee || !Number.isFinite(amount) || amount <= 0 || seen.has(id)) return; // skip blanks/zero; one per award
      seen.add(id);
      out.push({ payment_id: `USASPEND-UP-${id}`, payee, amount: Math.round(amount * 100) / 100 });
    });
    return { kind: "award", rows: out, errors: out.length ? [] : ["no screenable award rows found (need recipient_name and an award amount > 0)"] };
  }
  return { kind: null, rows: [], errors: ["unrecognized columns. Expected a payments file (payment_id, payee, amount) or a USAspending award file (recipient_name, an award id, an amount)."] };
}

// Serialize normalized rows to the payments CSV that Component E ingests.
export function toPaymentsCsv(rows) {
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  return "payment_id,payee,amount\n" + rows.map((r) => [r.payment_id, r.payee, r.amount].map(esc).join(",")).join("\n");
}
