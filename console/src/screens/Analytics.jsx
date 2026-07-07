import { useEffect, useState } from "react";
import { getAnalytics, getAuditLog } from "../lib/api.js";

const BAR = { approve: "var(--green)", review: "var(--amber)", reject: "var(--red)" };
const PILL = { approve: "approved", review: "pending", reject: "rejected" };

export default function Analytics() {
  const [a, setA] = useState(null);
  const [log, setLog] = useState(null);
  const [dispFilter, setDispFilter] = useState("all");
  const [err, setErr] = useState("");

  useEffect(() => { getAnalytics().then(setA).catch((e) => setErr(String(e.message || e))); }, []);
  useEffect(() => { getAuditLog({ disposition: dispFilter, limit: 200 }).then(setLog).catch(() => {}); }, [dispFilter]);

  if (err) return <div className="body"><div className="verdict bad">Failed to load analytics: {err}</div></div>;
  if (!a) return <div className="body"><div className="sub">Loading analytics…</div></div>;

  const mix = a.disposition_mix || {};
  const total = a.total_screened || 0;
  const throughput = a.throughput || [];
  const maxDay = Math.max(1, ...throughput.map((t) => t.count));

  const exportCsv = () => {
    const rows = [["payment_id", "disposition", "audited_at", "audit_key"],
      ...(log?.entries || []).map((e) => [e.payment_id, e.disposition, e.audited_at, e.key])];
    const csv = rows.map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url; link.download = "audit-log.csv"; link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="body">
      <h2>Audit log &amp; compliance</h2>
      <div className="sub">
        The immutable audit log for auditor export, plus screening throughput and reviewer
        productivity. Headline counters live on the Dashboard.
      </div>

      <div className="detail-grid">
        <div className="panel">
          <h3>Disposition mix</h3>
          {["approve", "review", "reject"].map((d) => {
            const n = Number(mix[d] || 0);
            const pct = total ? Math.round(100 * n / total) : 0;
            return (
              <div key={d} style={{ marginBottom: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                  <span style={{ textTransform: "capitalize" }}>{d}</span><span className="mono">{n} · {pct}%</span>
                </div>
                <div style={{ background: "#e9e6df", borderRadius: 4, height: 12 }}>
                  <div style={{ width: `${pct}%`, background: BAR[d], height: 12, borderRadius: 4 }} />
                </div>
              </div>
            );
          })}
        </div>
        <div className="panel">
          <h3>Throughput (last 14 days)</h3>
          {throughput.length === 0 ? <div className="sub" style={{ margin: 0 }}>No data yet.</div> : (
            <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 96 }}>
              {throughput.map((t) => (
                <div key={t.day} title={`${t.day}: ${t.count}`} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end" }}>
                  <div style={{ width: "100%", background: "var(--navy)", height: `${Math.round(72 * t.count / maxDay) + 3}px`, borderRadius: "3px 3px 0 0" }} />
                  <span style={{ fontSize: 9, color: "#8a8272", marginTop: 3 }}>{t.day.slice(5)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <h3>Reviewer productivity</h3>
        {(a.reviewer_productivity || []).length === 0 ? <div className="sub" style={{ margin: 0 }}>No human decisions yet.</div> : (
          <table>
            <thead><tr><th>Reviewer (identity)</th><th>Decisions</th></tr></thead>
            <tbody>{a.reviewer_productivity.map((r, i) => (
              <tr key={i}><td className="mono" style={{ fontSize: 12 }}>{r.reviewer}</td><td>{r.decisions}</td></tr>
            ))}</tbody>
          </table>
        )}
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h3 style={{ margin: 0 }}>Audit log</h3>
          <div className="filters" style={{ marginBottom: 0 }}>
            {["all", "approve", "review", "reject"].map((f) => (
              <button key={f} className={`chip ${dispFilter === f ? "on" : ""}`} onClick={() => setDispFilter(f)}>
                {f[0].toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
          <button className="btn btn-primary btn-sm" style={{ marginLeft: "auto" }} onClick={exportCsv} disabled={!log?.entries?.length}>
            Export CSV
          </button>
        </div>
        {log?.truncated && <div className="note" style={{ marginTop: 6 }}>Showing the latest {log.count} records.</div>}
        <table style={{ marginTop: 10 }}>
          <thead><tr><th>Payment</th><th>Disposition</th><th>Audited</th></tr></thead>
          <tbody>
            {(log?.entries || []).map((e) => (
              <tr key={`${e.payment_id}-${e.audited_at}`}>
                <td className="mono">{e.payment_id}</td>
                <td><span className={`pill p-${PILL[e.disposition] || "pending"}`}>{e.disposition}</span></td>
                <td className="mono" style={{ fontSize: 12 }}>{String(e.audited_at || "").slice(0, 19)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
