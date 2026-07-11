import { useEffect, useState } from "react";
import { getAudit } from "../lib/api.js";
import { useNameMasker } from "../lib/pii.js";

// Display-only transaction detail. STRICT: every value is READ from the immutable
// audit record — nothing is computed, re-screened, re-hashed, or derived here. A
// field the record does not contain renders as "not recorded", never fabricated.
// (Amount lives in the record, per the field assessment; it is shown here rather
// than as an audit-log column so no pipeline field is added.)

const NR = <span className="nr">not recorded</span>;

const money = (v) =>
  typeof v === "number" && Number.isFinite(v)
    ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(v)
    : null;

export default function RecordDetail({ paymentId }) {
  const { mask } = useNameMasker();
  const [record, setRecord] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    let live = true;
    setRecord(null); setErr("");
    getAudit(paymentId)
      .then((d) => { if (live) setRecord(d.record); })
      .catch((e) => { if (live) setErr(String(e.message || e)); });
    return () => { live = false; };
  }, [paymentId]);

  if (err) return <div className="rd"><div className="verdict bad">Could not load record: {err}</div></div>;
  if (!record) return <div className="rd"><div className="sub" style={{ margin: 0 }}>Loading record…</div></div>;

  // All reads below are straight field lookups on the record — no computation.
  const payee = record.payment?.payee;
  const amount = money(record.payment?.amount);
  const tin = record.payment?.payee_tin;
  const ver = record.provenance?.reference_list_version;
  const matches = Array.isArray(record.evidence?.matches) ? record.evidence.matches : [];
  const score = record.decision?.risk_score;
  const disposition = record.decision?.disposition;
  const reasons = Array.isArray(record.decision?.reasons) ? record.decision.reasons : [];
  const hash = record.integrity?.sha256;
  const hashAlgo = record.integrity?.algorithm;

  // Plain-language one-liner, assembled only from recorded values.
  const summary = [
    ver != null ? `Screened against watchlist v${ver}` : "Screened against watchlist (version not recorded)",
    matches.length ? `${matches.length} match${matches.length === 1 ? "" : "es"} found` : "no match found",
    score != null ? `score ${score}` : "score not recorded",
    disposition || "disposition not recorded",
    hash ? `recorded at ${hash.slice(0, 8)}…` : "hash not recorded",
  ].join(" — ");

  return (
    <div className="rd">
      <div className="rd-summary">{summary}</div>

      <div className="rd-cols">
        <dl className="rd-dl">
          <dt>Payment ID</dt><dd className="mono">{record.payment_id || NR}</dd>
          <dt>Payee</dt><dd>{payee ? mask(payee) : NR}</dd>
          <dt>Amount</dt><dd className="mono">{amount || NR}</dd>
          <dt>Payee TIN</dt><dd className="mono">{tin || NR}</dd>
          <dt>Watchlist version screened</dt><dd>{ver != null ? `v${ver}` : NR}</dd>
          <dt>Recorded at</dt><dd className="mono">{record.audited_at || NR}</dd>
        </dl>

        <dl className="rd-dl">
          <dt>Disposition</dt>
          <dd>{disposition ? <span className={`pill p-${disposition === "approve" ? "approved" : disposition === "reject" ? "rejected" : "pending"}`}>{disposition}</span> : NR}</dd>
          <dt>Score</dt><dd className="mono">{score != null ? score : NR}</dd>
          <dt>Reason</dt>
          <dd>{reasons.length ? <ul className="rd-reasons">{reasons.map((r, i) => <li key={i}>{r}</li>)}</ul> : NR}</dd>
          <dt>Match result</dt>
          <dd>
            {matches.length === 0 ? "No match found" : (
              <div className="rd-matches">
                {matches.map((m, i) => (
                  <div className="matchcard" key={i}>
                    <b>{(m.matched_on || "match").replace(/_/g, " ")}</b> on {m.source || NR}{" "}
                    <span style={{ color: "#6b6455" }}>
                      (severity {m.severity ?? "—"}, confidence {m.confidence ?? "—"}
                      {m.similarity != null ? `, similarity ${m.similarity}` : ""})
                    </span>
                  </div>
                ))}
              </div>
            )}
          </dd>
        </dl>
      </div>

      <div className="rd-integrity">
        <div className="rd-ilabel">Tamper-evident record hash ({hashAlgo || "sha-256"}) — read from the record, not recomputed</div>
        <div className="hashbox">{hash || NR}</div>
      </div>
    </div>
  );
}
