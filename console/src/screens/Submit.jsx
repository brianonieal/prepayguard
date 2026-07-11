import { useRef, useState } from "react";
import { parseCsv, parseJsonPayments } from "../lib/csv.js";
import { submitPayment, presignBatch, uploadFile, getBatch } from "../lib/api.js";
import { useNameMasker } from "../lib/pii.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export default function Submit() {
  const { mask } = useNameMasker();
  const [form, setForm] = useState({ payment_id: "", payee: "", payee_tin: "", amount: "" });
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");
  const [batch, setBatch] = useState(null);      // { name, file, rows, errors }
  const [batchState, setBatchState] = useState(null); // null | "uploading" | "processing" | summary | {error}
  const fileRef = useRef();
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onFile = (file) => {
    if (!file) return;
    setBatchState(null);
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    if (ext === "csv" || ext === "json") {
      const reader = new FileReader();
      reader.onload = () => {
        const { rows, errors } = (ext === "csv" ? parseCsv : parseJsonPayments)(String(reader.result));
        setBatch({ name: file.name, file, rows, errors, preview: true });
      };
      reader.readAsText(file);
    } else {
      // Excel (.xlsx) and anything else are parsed server-side by Component E.
      setBatch({ name: file.name, file, rows: [], errors: [], preview: false });
    }
  };

  // Server-side ingestion (v1.6.0): presign → upload the raw CSV to S3 →
  // Component E parses + enqueues → poll the batch summary. One upload, not
  // one request per row; duplicates dedupe against the single-API path too.
  const submitBatch = async () => {
    setBatchState("uploading");
    try {
      const { upload_url, batch_id } = await presignBatch(batch.file.name);
      await uploadFile(upload_url, batch.file);
      setBatchState("processing");
      for (let i = 0; i < 20; i++) {
        const s = await getBatch(batch_id);
        if (s.status === "complete") { setBatchState(s); return; }
        await sleep(1500);
      }
      setBatchState({ error: "Still processing. Check the review queue shortly." });
    } catch (ex) {
      setBatchState({ error: ex?.message || "batch upload failed" });
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

  const summary = batchState && batchState.status === "complete" ? batchState : null;
  const busy = batchState === "uploading" || batchState === "processing";

  return (
    <div className="body">
      <h2>Submit payments for screening</h2>
      <div className="sub">
        Screened against Do-Not-Pay reference sources before disbursement. Duplicates replay the
        original result (idempotent), so resubmitting a file is safe.
      </div>

      <div className="dropzone" onClick={() => fileRef.current.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); onFile(e.dataTransfer.files[0]); }}>
        <input ref={fileRef} type="file" data-testid="csv-input"
          onChange={(e) => onFile(e.target.files[0])} />
        <b>Upload a batch payment file.</b> Drag CSV, Excel, or JSON here or click to browse
        <div style={{ fontSize: 12, marginTop: 4 }}>
          fields: <span className="mono">payment_id, payee, payee_tin (optional), amount</span> · other file types are reported, not screened
        </div>
      </div>

      {batch && (
        <div style={{ maxWidth: 760, marginTop: 16 }}>
          <div className="sub" style={{ marginBottom: 8 }}>
            <b>{batch.name}</b>
            {batch.preview
              ? <> · {batch.rows.length} payment{batch.rows.length === 1 ? "" : "s"} parsed
                {batch.errors.length > 0 && <span style={{ color: "var(--red)" }}> · {batch.errors.length} skipped</span>}</>
              : <> · parsed server-side on upload</>}
          </div>

          {batch.preview && batch.rows.length > 0 && (
            <table>
              <thead><tr><th>Payment</th><th>Payee</th><th>TIN</th><th>Amount</th></tr></thead>
              <tbody>
                {batch.rows.slice(0, 100).map((r) => (
                  <tr key={r.payment_id}>
                    <td className="mono">{r.payment_id}</td><td>{mask(r.payee)}</td>
                    <td className="mono">{r.payee_tin || "-"}</td><td>${r.amount.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {batch.preview && batch.errors.length > 0 && !summary && (
            <ul className="note" style={{ marginTop: 8 }}>
              {batch.errors.slice(0, 5).map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}

          {!summary && (!batch.preview || batch.rows.length > 0) && (
            <button className="btn btn-primary" style={{ marginTop: 12 }} disabled={busy} onClick={submitBatch}>
              {batchState === "uploading" ? "Uploading…" : batchState === "processing" ? "Ingesting…"
                : batch.preview ? `Submit ${batch.rows.length} payment${batch.rows.length === 1 ? "" : "s"}` : `Upload ${batch.name}`}
            </button>
          )}

          {batchState && batchState.error && (
            <div className="verdict bad" style={{ marginTop: 12 }}>{batchState.error}</div>
          )}

          {summary && (
            <div className="result-ok" style={{ marginTop: 12 }}>
              <b>{summary.format === "unsupported" ? "Unsupported file format." : "Batch ingested."}</b>{" "}
              {summary.format !== "unsupported" && <>{summary.queued} queued for screening</>}
              {Number(summary.duplicate) > 0 && <> · {summary.duplicate} duplicate{Number(summary.duplicate) === 1 ? "" : "s"} (already screened)</>}
              {Number(summary.rejected) > 0 && <> · <span style={{ color: "var(--red)" }}>{summary.rejected} rejected</span></>}
              {summary.format && summary.format !== "unsupported" && <> · <span className="mono" style={{ fontSize: 12 }}>{summary.format}</span></>}
              . Flagged payments appear in the Review Queue.
              {Array.isArray(summary.errors) && summary.errors.length > 0 && (
                <ul style={{ marginTop: 6 }}>{summary.errors.slice(0, 5).map((e, i) => <li key={i}>{e}</li>)}</ul>
              )}
            </div>
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
          {result.idempotent_replay && " (idempotent replay, already screened)"}. Flagged payments appear in the Review Queue.
        </div>
      )}
      <div className="note">
        Batch files upload once and are ingested server-side (Component E). The same payment-ID
        idempotency applies, so a payment in both a file and a single submit is screened once.
      </div>
    </div>
  );
}
