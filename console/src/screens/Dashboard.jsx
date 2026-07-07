import { useEffect, useState } from "react";
import { getShowcase } from "../lib/api.js";
import { Donut, Gauge, FlagBars, DISPO } from "./Showcase.jsx";

// Operations dashboard: the live, at-a-glance picture. Plain-English KPI cards on
// top of the flagged-item hero, then the outcome donut, the flagged gauge, and the
// match-type breakdown. The narrative walkthrough moved to the Tour (see Tour.jsx).
export default function Dashboard({ onNav }) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { getShowcase().then(setData).catch((e) => setErr(String(e.message || e))); }, []);

  if (err) return <div className="body"><div className="verdict bad">Could not load the dashboard: {err}</div></div>;
  if (!data) return <div className="body"><div className="sub">Loading the live picture...</div></div>;

  const s = data.summary || {};
  const mix = s.disposition_mix || {};
  const total = s.total_screened || 0;
  const pending = s.queue?.pending ?? 0;

  const KPIS = [
    { k: "Payments checked", v: total.toLocaleString(), d: "screened before payout", c: "var(--navy)" },
    { k: "Flagged for risk", v: `${s.hit_rate ?? 0}%`, d: "stopped or sent to a person", c: "var(--amber)" },
    { k: "Stopped before payout", v: mix.reject || 0, d: "blocked automatically", c: "var(--red)" },
    { k: "Waiting on a person", v: pending, d: "in the review queue", c: "var(--copper)" },
  ];

  return (
    <div className="body">
      <div className="dash-head">
        <div>
          <h2>Operations dashboard</h2>
          <div className="sub" style={{ marginBottom: 0 }}>A live picture of everything PrePayGuard has screened.</div>
        </div>
        <span className="live-dot">live</span>
      </div>

      {pending > 0 && (
        <div className="hero-flag" data-testid="flag-hero">
          <div className="hero-flag-badge">{pending}</div>
          <div className="hero-flag-txt">
            <b>payment{pending === 1 ? "" : "s"} awaiting human review.</b>
            <span>Cases the risk engine could not clear or reject with confidence.</span>
          </div>
          <button className="btn btn-primary btn-sm" onClick={() => onNav("#/reviews")}>Go to review queue →</button>
        </div>
      )}

      <div className="kpi-row">
        {KPIS.map((x) => (
          <div key={x.k} className="kpi" style={{ borderLeftColor: x.c }}>
            <div className="kpi-k">{x.k}</div>
            <div className="kpi-v">{x.v}</div>
            <div className="kpi-d">{x.d}</div>
          </div>
        ))}
      </div>

      <div className="detail-grid" style={{ marginTop: 16 }}>
        <div className="panel">
          <h3>Outcome mix</h3>
          <div className="sc-donut-row">
            <Donut mix={mix} total={total} />
            <div className="sc-legend">
              {["approve", "review", "reject"].map((d) => {
                const n = Number(mix[d] || 0);
                const pct = total ? Math.round(100 * n / total) : 0;
                return (
                  <div key={d} className="sc-leg">
                    <span className="sc-dot" style={{ background: DISPO[d].color }} />
                    <span>{DISPO[d].label}</span>
                    <span className="mono sc-legn">{n} · {pct}%</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        <div className="panel">
          <h3>Flagged for risk</h3>
          <Gauge value={s.hit_rate} />
          <div className="setdesc" style={{ textAlign: "center" }}>Share stopped or sent to a person.</div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <h3>What the screening found</h3>
        <FlagBars matchTypes={data.match_types || {}} sample={data.match_sample_size || 0} />
      </div>

      <div className="panel tour-nudge" style={{ marginTop: 16 }}>
        <div>
          <b>New to PrePayGuard?</b>
          <div className="setdesc" style={{ marginTop: 3 }}>A quick, plain-English walkthrough of what it does and how to use it.</div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={() => onNav("#/tour")}>Take the 2-minute tour →</button>
      </div>
    </div>
  );
}
