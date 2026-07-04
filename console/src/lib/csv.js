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
