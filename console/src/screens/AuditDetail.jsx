import { useEffect, useRef, useState } from "react";
import { FAKE_AUDIT, FAKE_REVIEWS } from "../fakeData.js";
import { hashRecord } from "../lib/integrity.js";
import { explainScore } from "../lib/score.js";

const FAKE_ATTACHMENTS = [
  { name: "debt-satisfaction-letter.pdf", size: "182 KB", by: "brian.onieal@gmail.com", at: "2026-07-03" },
];

export default function AuditDetail({ paymentId, onBack }) {
  const review = FAKE_REVIEWS.find((r) => r.payment_id === paymentId) || FAKE_REVIEWS[0];
  const audit = FAKE_AUDIT;
  const [note, setNote] = useState("");
  const [decided, setDecided] = useState(null);
  const [attachments, setAttachments] = useState(FAKE_ATTACHMENTS);
  const [tampered, setTampered] = useState(false);
  const [storedHash, setStoredHash] = useState(null);
  const [verify, setVerify] = useState(null); // {ok, recomputed}
  const fileRef = useRef();
  const status = decided || review.status;

  // "Stored" hash = what was written at audit time. In this static gate we
  // compute it once from the untampered record; live records (v1.4.0) carry
  // the pipeline's stored hash.
  useEffect(() => { hashRecord(audit).then(setStoredHash); }, [audit]);

  const currentRecord = tampered
    ? { ...audit, decision: { ...audit.decision, risk_score: 99 } }
    : audit;

  const runVerify = async () => {
    const recomputed = await hashRecord(currentRecord);
    setVerify({ recomputed, ok: recomputed === storedHash });
  };

  const addAttachment = (file) => {
    if (!file) return;
    setAttachments((a) => [...a, { name: file.name, size: `${Math.max(1, Math.round(file.size / 1024))} KB`, by: "you", at: "now" }]);
  };

  const { best, band, steps } = explainScore(audit);

  return (
    <div className="body">
      <button className="rowlink" onClick={onBack}>← Back to queue</button>
      <h2 className="mono" style={{ fontSize: 17, marginTop: 10 }}>
        {review.payment_id} <span className={`pill p-${status}`} style={{ verticalAlign: 3 }}>{status}</span>
      </h2>
      <div className="sub">{review.payee} · ${Number(audit.payment.amount).toFixed(2)} · received {audit.audited_at}</div>

      <div className="detail-grid">
        <div>
          <div className="panel">
            <h3>Screening evidence</h3>
            {audit.evidence.matches.map((m, i) => (
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
                  {" = "}<b>{s.raw}</b>{s.capped && <span className="capnote"> → capped at 60 (name match)</span>}
                  {" → "}<b>{s.value}</b>
                </div>
              ))}
              <div className="bandbar">
                <div className="bandzone z-approve" />
                <div className="bandzone z-review" />
                <div className="bandzone z-reject" />
                <span className="bandpin" style={{ left: `${best}%` }} title={`score ${best}`} />
                <span className="bandtick" style={{ left: "30%" }}><i>30</i></span>
                <span className="bandtick" style={{ left: "80%" }}><i>80</i></span>
              </div>
              <div className="bandkey"><span className="k-a">approve &lt;30</span><span className="k-r">review 30–79</span><span className="k-x">reject ≥80</span></div>
            </div>
          </div>

          {status === "pending" && (
            <div className="panel" style={{ marginTop: 14 }}>
              <h3>Decision</h3>
              <div className="decide">
                <textarea aria-label="Adjudication note"
                  placeholder="Adjudication note (recorded in the decision audit record)…"
                  value={note} onChange={(e) => setNote(e.target.value)} />
                <div className="stack">
                  <button className="btn btn-green" onClick={() => setDecided("approved")}>Approve payment</button>
                  <button className="btn btn-red" onClick={() => setDecided("rejected")}>Reject payment</button>
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
            {attachments.map((a, i) => (
              <div className="attach" key={i}>
                <div className="icon">PDF</div><div>{a.name}</div>
                <div className="meta">{a.size}<br />{a.by} · {a.at}</div>
              </div>
            ))}
            <input ref={fileRef} type="file" style={{ display: "none" }} data-testid="attach-input"
                   onChange={(e) => addAttachment(e.target.files[0])} />
            <button className="btn btn-primary btn-sm" onClick={() => fileRef.current.click()}>+ Attach document</button>
            <div style={{ fontSize: 12, color: "#6b6455", marginTop: 8 }}>
              Documents are stored with the case and referenced by the decision audit record.
            </div>
          </div>

          <div className="panel">
            <h3>Audit record</h3>
            <dl>
              <dt>audit_id</dt><dd className="mono">{audit.audit_id}</dd>
              <dt>audited_at</dt><dd className="mono">{audit.audited_at}</dd>
              <dt>pipeline</dt><dd className="mono">{audit.provenance.pipeline.join(" → ")}</dd>
              <dt>storage</dt><dd>S3 Object Lock · COMPLIANCE</dd>
            </dl>
            <div className="hashbox">stored sha-256: {storedHash || "computing…"}</div>
            <div className="verifybar">
              <button className="btn btn-sm btn-primary" onClick={runVerify} disabled={!storedHash}>Verify integrity</button>
              <label className="tamper"><input type="checkbox" checked={tampered}
                onChange={(e) => { setTampered(e.target.checked); setVerify(null); }} /> simulate tampering</label>
            </div>
            {verify && (
              <div className={`verdict ${verify.ok ? "ok" : "bad"}`}>
                {verify.ok
                  ? "✓ integrity verified — recomputed hash matches the stored hash"
                  : "✗ integrity FAILED — recomputed hash does not match; record was altered"}
                <div className="hashbox" style={{ marginTop: 6 }}>recomputed: {verify.recomputed}</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
