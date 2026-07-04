import { useEffect, useState } from "react";
import { listReviews } from "../lib/api.js";

const AGE_H = (iso) => Math.max(0, Math.round((Date.now() - new Date(iso)) / 3.6e6));
const AGE = (iso) => {
  const h = AGE_H(iso);
  return h < 1 ? "just now" : h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
};

export default function ReviewQueue({ onOpen, defaultFilter = "pending" }) {
  const [reviews, setReviews] = useState(null);
  const [err, setErr] = useState("");
  const [status, setStatus] = useState(defaultFilter);
  const [query, setQuery] = useState("");
  const [window_, setWindow] = useState("all");

  useEffect(() => {
    listReviews().then((d) => setReviews(d.reviews || [])).catch((e) => setErr(String(e.message || e)));
  }, []);

  if (err) return <div className="body"><div className="verdict bad">Failed to load reviews: {err}</div></div>;
  if (reviews === null) return <div className="body"><div className="sub">Loading review queue…</div></div>;

  const counts = reviews.reduce((a, r) => ({ ...a, [r.status]: (a[r.status] || 0) + 1 }), {});
  const q = query.trim().toLowerCase();
  const rows = reviews.filter((r) => {
    if (status !== "all" && r.status !== status) return false;
    if (window_ !== "all" && AGE_H(r.received_at) > Number(window_) * 24) return false;
    if (q && !`${r.payment_id} ${r.payee || ""}`.toLowerCase().includes(q)) return false;
    return true;
  });
  const pend = reviews.filter((r) => r.status === "pending");
  const avg = pend.length ? Math.round(pend.reduce((s, r) => s + Number(r.score), 0) / pend.length) : "—";
  const oldest = pend.length ? AGE(pend.map((r) => r.received_at).sort()[0]) : "—";

  return (
    <div className="body">
      <h2>Human review queue</h2>
      <div className="sub">
        Payments the risk engine could not clear or reject with confidence. Each decision is written
        to the immutable audit log.
      </div>
      <div className="stats">
        <div className="stat warn"><div className="k">Pending review</div><div className="v">{counts.pending || 0}</div><div className="d">awaiting adjudication</div></div>
        <div className="stat"><div className="k">Avg risk score (pending)</div><div className="v">{avg}</div><div className="d">review band: 30–79</div></div>
        <div className="stat"><div className="k">Oldest pending</div><div className="v">{oldest}</div><div className="d">age alarm at 4h (DEC-7 fallback)</div></div>
      </div>
      <div className="toolbar">
        <input className="search" placeholder="Search payment ID or payee…" value={query}
          onChange={(e) => setQuery(e.target.value)} aria-label="Search reviews" />
        <select value={window_} onChange={(e) => setWindow(e.target.value)} aria-label="Date range">
          <option value="all">All time</option><option value="1">Last 24h</option><option value="7">Last 7 days</option>
        </select>
      </div>
      <div className="filters">
        {["pending", "approved", "rejected", "all"].map((f) => (
          <button key={f} className={`chip ${status === f ? "on" : ""}`} onClick={() => setStatus(f)}>
            {f[0].toUpperCase() + f.slice(1)} ({f === "all" ? reviews.length : counts[f] || 0})
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <div className="empty">No payments match these filters.</div>
      ) : (
        <table>
          <thead><tr><th>Payment</th><th>Payee</th><th>Match</th><th>Score</th><th>Received</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.payment_id}>
                <td className="mono">{r.payment_id}</td>
                <td>{r.payee || "—"}</td>
                <td>{r.match || "—"}</td>
                <td><span className="score s-mid">{r.score}</span></td>
                <td>{AGE(r.received_at)}</td>
                <td><span className={`pill p-${r.status}`}>{r.status}</span></td>
                <td><button className="rowlink" onClick={() => onOpen(r.payment_id)}>
                  {r.status === "pending" ? "Review →" : "View →"}
                </button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
