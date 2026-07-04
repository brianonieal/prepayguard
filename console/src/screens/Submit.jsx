import { useRef, useState } from "react";
import { parseCsv } from "../lib/csv.js";
import { submitPayment } from "../lib/api.js";

export default function Submit() {
  const [form, setForm] = useState({ payment_id: "", payee: "", payee_tin: "", amount: "" });
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");
  const [batch, setBatch] = useState(null);
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

  const setRow = (i, state) => setBatch((b) => {
    const rows = [...b.rows];
    rows[i] = { ...rows[i], state };
    return { ...b, rows };
  });

  const submitBatch = async () => {
    for (let i = 0; i < batch.rows.length; i++) {
      const r = batch.rows[i];
      setRow(i, "sending");
      try {
        await submitPayment({ payment_id: r.payment_id, payee: r.payee, payee_tin: r.payee_tin || undefined, amount: r.amount });
        setRow(i, "queued");
      } catch {
        setRow(i, "error");
      }
    }
  };

  const submitOne = async (e) => {
    e.preventDefault();
    setErr(""); setResult(null);
    try {
      const r = await submitPayment({
        payment_id: form.payment_id, payee: form.payee,
        payee_tin: form.payee_tin || undefined, amount: Number(form.amount),
      });
      setResult(r);
    } catch (ex) {
      setErr(ex?.message || "submit failed");
    }
  };

  return (
    <div className="body">
      <h2>Submit payments for screening</h2>
      <div className="sub">
        Screened against Do-Not-Pay reference sources before disbursement. Duplicates replay the
        original result (idempotent) — resubmitting a file is safe.
      </div>

      <div className="dropzone" onClick={() => fileRef.current.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); onFile(e.dataTransfer.files[0]); }}>
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
            {batch.errors.length > 0 && <span style={{ color: "var(--red)" }}> · {batch.errors.length} skipped</span>}
          </div>
          <table>
            <thead><tr><th>Payment</th><th>Payee</th><th>TIN</th><th>Amount</th><th>State</th></tr></thead>
            <tbody>
              {batch.rows.map((r) => (
                <tr key={r.payment_id}>
                  <td className="mono">{r.payment_id}</td><td>{r.payee}</td>
                  <td className="mono">{r.payee_tin || "—"}</td><td>${r.amount.toFixed(2)}</td>
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

      {err && <div className="verdict bad" style={{ maxWidth: 640 }}>{err}</div>}
      <form onSubmit={submitOne}>
        <div className="grid2">
          <div><label htmlFor="pid">Payment ID</label>
            <input id="pid" className="mono" value={form.payment_id} onChange={set("payment_id")} required /></div>
          <div><label htmlFor="amount">Amount (USD)</label>
            <input id="amount" value={form.amount} onChange={set("amount")} required /></div>
          <div><label htmlFor="payee">Payee name</label>
            <input id="payee" value={form.payee} onChange={set("payee")} required /></div>
          <div><label htmlFor="tin">Payee TIN (optional)</label>
            <input id="tin" className="mono" value={form.payee_tin} onChange={set("payee_tin")} /></div>
        </div>
        <button className="btn btn-primary" style={{ marginTop: 20 }} type="submit">Submit for screening</button>
      </form>
      {result && (
        <div className="result-ok">
          <b>Queued.</b> <span className="mono">message_id {result.message_id}</span>
          {result.idempotent_replay && " (idempotent replay — already screened)"} — flagged payments appear in the Review Queue.
        </div>
      )}
      <div className="note">
        Requests are SigV4-signed with your temporary credentials and validated at the API edge
        (schema + payment-ID idempotency).
      </div>
    </div>
  );
}
