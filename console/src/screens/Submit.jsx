import { useRef, useState } from "react";
import { parseCsv } from "../lib/csv.js";

export default function Submit() {
  const [form, setForm] = useState({ payment_id: "", payee: "", payee_tin: "", amount: "" });
  const [result, setResult] = useState(null);
  const [batch, setBatch] = useState(null); // {name, rows:[{...row, state}], errors}
  const fileRef = useRef();
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onFile = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const { rows, errors } = parseCsv(String(reader.result));
      setBatch({ name: file.name, errors, rows: rows.map((r) => ({ ...r, state: "staged" })) });
    };
    reader.readAsText(file);
  };

  const submitBatch = () => {
    // Static gate: fake per-row queueing. v1.4.0 loops SigV4 POSTs to the
    // idempotent intake API (safe to retry a partially-submitted file).
    setBatch((b) => ({ ...b, rows: b.rows.map((r) => ({ ...r, state: "queued" })) }));
  };

  return (
    <div className="body">
      <h2>Submit payments for screening</h2>
      <div className="sub">
        Screened against Do-Not-Pay reference sources before disbursement. Duplicates replay the
        original result (idempotent) — resubmitting a file is safe.
      </div>

      <div
        className="dropzone"
        onClick={() => fileRef.current.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); onFile(e.dataTransfer.files[0]); }}
      >
        <input ref={fileRef} type="file" accept=".csv" data-testid="csv-input"
               onChange={(e) => onFile(e.target.files[0])} />
        <b>Upload a batch payment file</b> — drag a CSV here or click to browse
        <div style={{ fontSize: 12, marginTop: 4 }}>
          columns: <span className="mono">payment_id, payee, payee_tin (optional), amount</span>
        </div>
      </div>

      {batch && (
        <div style={{ maxWidth: 760, marginTop: 16 }}>
          <div className="sub" style={{ marginBottom: 8 }}>
            <b>{batch.name}</b> — {batch.rows.length} payment{batch.rows.length === 1 ? "" : "s"} parsed
            {batch.errors.length > 0 && <span style={{ color: "var(--red)" }}> · {batch.errors.length} row error{batch.errors.length === 1 ? "" : "s"} skipped</span>}
          </div>
          {batch.errors.length > 0 && (
            <div className="note" style={{ borderLeftColor: "var(--red)", marginTop: 0, marginBottom: 10 }}>
              {batch.errors.map((e, i) => <div key={i} className="mono" style={{ fontSize: 12 }}>{e}</div>)}
            </div>
          )}
          <table>
            <thead><tr><th>Payment</th><th>Payee</th><th>TIN</th><th>Amount</th><th>State</th></tr></thead>
            <tbody>
              {batch.rows.map((r) => (
                <tr key={r.payment_id}>
                  <td className="mono">{r.payment_id}</td>
                  <td>{r.payee}</td>
                  <td className="mono">{r.payee_tin || "—"}</td>
                  <td>${r.amount.toFixed(2)}</td>
                  <td><span className={`rowstate r-${r.state}`}>{r.state}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          {batch.rows.some((r) => r.state === "staged") && (
            <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={submitBatch}>
              Submit {batch.rows.length} payment{batch.rows.length === 1 ? "" : "s"}
            </button>
          )}
        </div>
      )}

      <div className="section-split">or submit a single payment</div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setResult({ message_id: "static-preview-0000" }); // v1.4.0 wires the intake API
        }}
      >
        <div className="grid2">
          <div>
            <label htmlFor="pid">Payment ID</label>
            <input id="pid" className="mono" value={form.payment_id} onChange={set("payment_id")} required />
          </div>
          <div>
            <label htmlFor="amount">Amount (USD)</label>
            <input id="amount" value={form.amount} onChange={set("amount")} required />
          </div>
          <div>
            <label htmlFor="payee">Payee name</label>
            <input id="payee" value={form.payee} onChange={set("payee")} required />
          </div>
          <div>
            <label htmlFor="tin">Payee TIN (optional)</label>
            <input id="tin" className="mono" value={form.payee_tin} onChange={set("payee_tin")} />
          </div>
        </div>
        <button className="btn btn-primary" style={{ marginTop: 20 }} type="submit">
          Submit for screening
        </button>
      </form>
      {result && (
        <div className="result-ok">
          <b>Queued.</b> <span className="mono">message_id {result.message_id}</span> — screening runs
          asynchronously; flagged payments appear in the Review Queue.
        </div>
      )}
      <div className="note">
        Requests are SigV4-signed with your temporary credentials and validated at the API edge
        (schema + payment-ID idempotency).
      </div>
    </div>
  );
}
