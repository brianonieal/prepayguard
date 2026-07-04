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
