import { useEffect, useRef, useState } from "react";
import { decide, getAudit, listAttachments, listReviews, presignAttachment, uploadFile } from "../lib/api.js";
import { hashRecord } from "../lib/integrity.js";
import { explainScore } from "../lib/score.js";

export default function AuditDetail({ paymentId, onBack }) {
  const [record, setRecord] = useState(null);
  const [status, setStatus] = useState(null);
  const [attachments, setAttachments] = useState([]);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [tampered, setTampered] = useState(false);
  const [verify, setVerify] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef();

  useEffect(() => {
    getAudit(paymentId).then((d) => setRecord(d.record)).catch((e) => setErr(String(e.message || e)));
    listReviews().then((d) => {
      const row = (d.reviews || []).find((r) => r.payment_id === paymentId);
      setStatus(row?.status || "pending");
    }).catch(() => setStatus("pending"));
    listAttachments(paymentId).then((d) => setAttachments(d.attachments || [])).catch(() => {});
  }, [paymentId]);

  if (err) return <div className="body"><button className="rowlink" onClick={onBack}>← Back</button><div className="verdict bad" style={{ marginTop: 10 }}>{err}</div></div>;
  if (!record) return <div className="body"><div className="sub">Loading case…</div></div>;

  const current = tampered ? { ...record, decision: { ...record.decision, risk_score: 99 } } : record;
  const runVerify = async () => {
    const recomputed = await hashRecord(current);
    setVerify({ recomputed, ok: recomputed === record.integrity?.sha256 });
  };
  const doDecide = async (decision) => {
    setBusy(true); setErr("");
    try { await decide(paymentId, { decision, note }); setStatus(decision); }
    catch (ex) { setErr(ex?.message || "decision failed"); }
    finally { setBusy(false); }
  };
  const doAttach = async (file) => {
    if (!file) return;
    try {
      const { upload_url } = await presignAttachment(paymentId, file.name, file.type);
      await uploadFile(upload_url, file);
      setAttachments((await listAttachments(paymentId)).attachments || []);
    } catch (ex) { setErr(ex?.message || "upload failed"); }
  };

  const { best, band, steps } = explainScore(record);

  return (
    <div className="body">
      <button className="rowlink" onClick={onBack}>← Back to queue</button>
      <h2 className="mono" style={{ fontSize: 17, marginTop: 10 }}>
        {record.payment_id} <span className={`pill p-${status || "pending"}`} style={{ verticalAlign: 3 }}>{status || "…"}</span>
      </h2>
      <div className="sub">{record.payment?.payee} · ${Number(record.payment?.amount ?? 0).toFixed(2)} · received {record.audited_at}</div>

      <div className="detail-grid">
        <div>
          <div className="panel">
            <h3>Screening evidence</h3>
            {record.evidence.matches.map((m, i) => (
              <div className="matchcard" key={i}>
                <b>{m.matched_on.replace("_", " ")} match</b> — {m.source}{" "}
                <span style={{ color: "#6b6455" }}>(severity {m.severity}, confidence {m.confidence})</span>
              </div>
            ))}
            <div className="explain">
              <div className="explain-h">Why score {best} → {band}</div>
              {steps.map((s, i) => (
                <div className="explain-row" key={i}>
                  <span className="mono">{s.matched_on}</span> conf {s.confidence} × {s.severity} weight {s.weight}
                  {" = "}<b>{s.raw}</b>{s.capped && <span className="capnote"> → capped at 60</span>}{" → "}<b>{s.value}</b>
                </div>
              ))}
              <div className="bandbar">
                <div className="bandzone z-approve" /><div className="bandzone z-review" /><div className="bandzone z-reject" />
                <span className="bandpin" style={{ left: `${best}%` }} />
                <span className="bandtick" style={{ left: "30%" }}><i>30</i></span>
                <span className="bandtick" style={{ left: "80%" }}><i>80</i></span>
              </div>
              <div className="bandkey"><span>approve &lt;30</span><span>review 30–79</span><span>reject ≥80</span></div>
            </div>
          </div>

          {status === "pending" && (
            <div className="panel" style={{ marginTop: 14 }}>
              <h3>Decision</h3>
              {err && <div className="verdict bad" style={{ marginBottom: 10 }}>{err}</div>}
              <div className="decide">
                <textarea aria-label="Adjudication note" placeholder="Adjudication note (recorded in the decision audit record)…"
                  value={note} onChange={(e) => setNote(e.target.value)} />
                <div className="stack">
                  <button className="btn btn-green" disabled={busy} onClick={() => doDecide("approved")}>Approve payment</button>
                  <button className="btn btn-red" disabled={busy} onClick={() => doDecide("rejected")}>Reject payment</button>
                </div>
              </div>
              <div className="note" style={{ maxWidth: "none", marginTop: 14 }}>
                Your decision writes an immutable, integrity-hashed audit record before the status
                changes. Decisions cannot be edited — a reversal is a new audited decision.
              </div>
            </div>
          )}
        </div>

        <div>
          <div className="panel" style={{ marginBottom: 14 }}>
            <h3>Case documents</h3>
            {attachments.length === 0 && <div className="sub" style={{ margin: 0 }}>No documents yet.</div>}
            {attachments.map((a, i) => (
              <div className="attach" key={i}>
                <div className="icon">DOC</div><div>{a.name}</div>
                <div className="meta">{Math.max(1, Math.round((a.size || 0) / 1024))} KB</div>
              </div>
            ))}
            <input ref={fileRef} type="file" style={{ display: "none" }} data-testid="attach-input"
              onChange={(e) => doAttach(e.target.files[0])} />
            <button className="btn btn-primary btn-sm" onClick={() => fileRef.current.click()}>+ Attach document</button>
          </div>

          <div className="panel">
            <h3>Audit record</h3>
            <dl>
              <dt>audit_id</dt><dd className="mono">{record.audit_id}</dd>
              <dt>audited_at</dt><dd className="mono">{record.audited_at}</dd>
              <dt>pipeline</dt><dd className="mono">{record.provenance.pipeline.join(" → ")}</dd>
              <dt>storage</dt><dd>S3 Object Lock · COMPLIANCE</dd>
            </dl>
            <div className="hashbox">stored sha-256: {record.integrity?.sha256}</div>
            <div className="verifybar">
              <button className="btn btn-sm btn-primary" onClick={runVerify}>Verify integrity</button>
              <label className="tamper"><input type="checkbox" checked={tampered}
                onChange={(e) => { setTampered(e.target.checked); setVerify(null); }} /> simulate tampering</label>
            </div>
            {verify && (
              <div className={`verdict ${verify.ok ? "ok" : "bad"}`}>
                {verify.ok ? "✓ integrity verified — recomputed hash matches" : "✗ integrity FAILED — record was altered"}
                <div className="hashbox" style={{ marginTop: 6 }}>recomputed: {verify.recomputed}</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
