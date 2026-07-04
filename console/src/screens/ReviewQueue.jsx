import { useEffect, useState } from "react";
import { listReviews } from "../lib/api.js";

const AGE_H = (iso) => Math.max(0, Math.round((Date.now() - new Date(iso)) / 3.6e6));
const AGE = (iso) => {
  const h = AGE_H(iso);
  return h < 1 ? "just now" : h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
};

export default function ReviewQueue({ onOpen, defaultFilter = "pending" }) {
  const [status, setStatus] = useState(defaultFilter);
  const [items, setItems] = useState(null);
  const [cursor, setCursor] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [query, setQuery] = useState("");

  const load = (reset) => {
    setLoading(true);
    listReviews({ status, cursor: reset ? null : cursor, limit: 25 })
      .then((d) => {
        setItems((prev) => (reset || prev === null ? (d.reviews || []) : [...prev, ...(d.reviews || [])]));
        setCursor(d.next_cursor || null);
      })
      .catch((e) => setErr(String(e.message || e)))
      .finally(() => setLoading(false));
  };

  // Refetch page 1 whenever the server-side status filter changes.
  useEffect(() => { setItems(null); setCursor(null); load(true); }, [status]); // eslint-disable-line

  if (err) return <div className="body"><div className="verdict bad">Failed to load reviews: {err}</div></div>;
  if (items === null) return <div className="body"><div className="sub">Loading review queue…</div></div>;

  const q = query.trim().toLowerCase();
  const rows = items.filter((r) => !q || `${r.payment_id} ${r.payee || ""}`.toLowerCase().includes(q));
  const pend = items.filter((r) => r.status === "pending");
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
        <div className="stat warn"><div className="k">Pending (loaded)</div><div className="v">{pend.length}</div><div className="d">awaiting adjudication</div></div>
        <div className="stat"><div className="k">Avg risk score (pending)</div><div className="v">{avg}</div><div className="d">review band: 30–79</div></div>
        <div className="stat"><div className="k">Oldest pending</div><div className="v">{oldest}</div><div className="d">age alarm at 4h (DEC-7 fallback)</div></div>
      </div>
      <div className="toolbar">
        <input className="search" placeholder="Search loaded payment ID or payee…" value={query}
          onChange={(e) => setQuery(e.target.value)} aria-label="Search reviews" />
      </div>
      <div className="filters">
        {["pending", "approved", "rejected", "all"].map((f) => (
          <button key={f} className={`chip ${status === f ? "on" : ""}`} onClick={() => setStatus(f)}>
            {f[0].toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <div className="empty">{loading ? "Loading…" : "No payments match."}</div>
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
      {cursor && (
        <div style={{ marginTop: 14 }}>
          <button className="btn btn-ghost" disabled={loading} onClick={() => load(false)}>
            {loading ? "Loading…" : "Load more"}
          </button>
        </div>
      )}
    </div>
  );
}
