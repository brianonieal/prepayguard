import { useEffect, useState } from "react";
import { getShowcase } from "../lib/api.js";

// v3.0.0 Executive Showcase — the narrative "Overview" tab. One live data call,
// hand-built SVG charts (no chart library), balanced for a Treasury exec and an
// academic reviewer. Everything below is real data from the running pipeline.

const DISPO = {
  approve: { label: "Approve", color: "var(--green)", pill: "p-approved" },
  review: { label: "Review", color: "var(--amber)", pill: "p-pending" },
  reject: { label: "Reject", color: "var(--red)", pill: "p-rejected" },
};

const MATCH_LABEL = {
  tin: "TIN — exact",
  name_exact: "Name — exact",
  name_fuzzy: "Name — fuzzy",
  name_semantic: "Name — semantic",
  none: "No match — cleared",
};
const MATCH_ORDER = ["tin", "name_exact", "name_fuzzy", "name_semantic", "none"];
const MATCH_COLOR = {
  tin: "var(--red)", name_exact: "var(--navy)", name_fuzzy: "var(--amber)",
  name_semantic: "var(--copper)", none: "#c7c2b6",
};

function fmtAmount(a) {
  const n = Number(a);
  return Number.isFinite(n)
    ? n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 })
    : String(a ?? "—");
}

// --- charts -----------------------------------------------------------------

function Donut({ mix, total }) {
  const r = 54, C = 2 * Math.PI * r;
  let acc = 0;
  const segs = ["approve", "review", "reject"].map((d) => {
    const n = Number(mix[d] || 0);
    const frac = total ? n / total : 0;
    const seg = { d, n, len: frac * C, offset: acc * C };
    acc += frac;
    return seg;
  });
  return (
    <svg viewBox="0 0 140 140" className="sc-donut" role="img" aria-label="Disposition mix">
      <g transform="rotate(-90 70 70)">
        <circle cx="70" cy="70" r={r} fill="none" stroke="#ece8df" strokeWidth="17" />
        {segs.filter((s) => s.len > 0.5).map((s) => (
          <circle key={s.d} cx="70" cy="70" r={r} fill="none" stroke={DISPO[s.d].color}
            strokeWidth="17" strokeDasharray={`${s.len} ${C - s.len}`} strokeDashoffset={-s.offset} />
        ))}
      </g>
      <text x="70" y="66" textAnchor="middle" className="sc-donut-num">{total}</text>
      <text x="70" y="85" textAnchor="middle" className="sc-donut-lbl">screened</text>
    </svg>
  );
}

function Gauge({ value }) {
  const r = 52, cx = 70, cy = 74;
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  const a = Math.PI * (1 - v / 100);
  const x = cx + r * Math.cos(a), y = cy - r * Math.sin(a);
  const big = v > 50 ? 1 : 0;
  return (
    <svg viewBox="0 0 140 92" className="sc-gauge" role="img" aria-label={`Hit rate ${v} percent`}>
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke="#ece8df" strokeWidth="13" strokeLinecap="round" />
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 ${big} 1 ${x} ${y}`} fill="none" stroke="var(--amber)" strokeWidth="13" strokeLinecap="round" />
      <text x={cx} y={cy - 6} textAnchor="middle" className="sc-donut-num">{v}%</text>
      <text x={cx} y={cy + 10} textAnchor="middle" className="sc-donut-lbl">flagged</text>
    </svg>
  );
}

function Timeline({ data }) {
  if (!data || data.length === 0) {
    return <div className="sub" style={{ margin: 0 }}>No screening activity recorded yet.</div>;
  }
  const W = 520, H = 128, padX = 6, padTop = 10, padBot = 22;
  const max = Math.max(1, ...data.map((d) => d.count));
  const bw = (W - padX * 2) / data.length;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="sc-timeline" preserveAspectRatio="none" role="img" aria-label="Screening throughput by day">
      {data.map((d, i) => {
        const h = Math.round((H - padTop - padBot) * (d.count / max)) + 2;
        const x = padX + i * bw;
        const y = H - padBot - h;
        return (
          <g key={d.day}>
            <rect x={x + 2} y={y} width={bw - 4} height={h} rx="2" fill="var(--navy)">
              <title>{`${d.day}: ${d.count}`}</title>
            </rect>
            <text x={x + bw / 2} y={H - 7} textAnchor="middle" className="sc-tick">{d.day.slice(5)}</text>
          </g>
        );
      })}
    </svg>
  );
}

function MatchTypeBars({ matchTypes, sample }) {
  const rows = MATCH_ORDER.filter((k) => (matchTypes[k] || 0) > 0).map((k) => ({ k, n: matchTypes[k] }));
  const total = rows.reduce((s, r) => s + r.n, 0);
  if (!total) return <div className="sub" style={{ margin: 0 }}>No records sampled yet.</div>;
  const max = Math.max(...rows.map((r) => r.n));
  return (
    <div className="sc-mtbars">
      {rows.map((r) => (
        <div key={r.k} className="sc-mtrow">
          <span className="sc-mtlabel">{MATCH_LABEL[r.k] || r.k}</span>
          <span className="sc-mttrack">
            <span className="sc-mtfill" style={{ width: `${Math.round(100 * r.n / max)}%`, background: MATCH_COLOR[r.k] }} />
          </span>
          <span className="sc-mtnum mono">{r.n}</span>
        </div>
      ))}
      <div className="setdesc" style={{ marginTop: 8 }}>
        How the {sample} most recent screenings were decided — the strongest signal per payment.
      </div>
    </div>
  );
}

function PipelineFlow() {
  const stages = [
    ["A", "Intake", "idempotent, queued"],
    ["B", "Enrichment", "rule + fuzzy + semantic"],
    ["C", "Risk scoring", "transparent score"],
    ["D", "Disposition", "approve / review / reject"],
  ];
  const NW = 150, NH = 62, GAP = 34, x0 = 10, y = 20;
  const totalW = x0 + stages.length * NW + (stages.length - 1) * GAP + 30;
  return (
    <svg viewBox={`0 0 ${totalW} 176`} className="sc-flow" role="img" aria-label="Pipeline flow">
      {stages.map(([tag, name, sub], i) => {
        const x = x0 + i * (NW + GAP);
        return (
          <g key={tag}>
            {i > 0 && (
              <line x1={x - GAP + 2} y1={y + NH / 2} x2={x - 3} y2={y + NH / 2} stroke="#b9b2a3" strokeWidth="2" markerEnd="url(#sc-arrow)" />
            )}
            <rect x={x} y={y} width={NW} height={NH} rx="8" fill="#fff" stroke="var(--line)" />
            <circle cx={x + 18} cy={y + NH / 2} r="11" fill="var(--navy)" />
            <text x={x + 18} y={y + NH / 2 + 4} textAnchor="middle" className="sc-flow-tag">{tag}</text>
            <text x={x + 38} y={y + 26} className="sc-flow-name">{name}</text>
            <text x={x + 38} y={y + 43} className="sc-flow-sub">{sub}</text>
          </g>
        );
      })}
      {/* audit sink under D + review branch */}
      {(() => {
        const dx = x0 + 3 * (NW + GAP);
        const auditY = y + NH + 42;
        return (
          <g>
            <line x1={dx + NW / 2} y1={y + NH} x2={dx + NW / 2} y2={auditY} stroke="#b9b2a3" strokeWidth="2" markerEnd="url(#sc-arrow)" />
            <rect x={dx} y={auditY} width={NW} height={NH} rx="8" fill="var(--navy)" />
            <text x={dx + NW / 2} y={auditY + 25} textAnchor="middle" className="sc-flow-name" fill="#fff">Immutable audit</text>
            <text x={dx + NW / 2} y={auditY + 43} textAnchor="middle" className="sc-flow-sub" fill="#adc0d6">S3 Object Lock · SHA-256</text>
            <line x1={dx - GAP + 2} y1={y + NH + 4} x2={dx - GAP + 2} y2={auditY + NH / 2} stroke="#d7b26a" strokeWidth="2" strokeDasharray="4 3" />
            <text x={dx - GAP - 44} y={auditY + NH / 2 + 4} className="sc-flow-sub" fill="var(--amber)">to reviewer</text>
          </g>
        );
      })()}
      <defs>
        <marker id="sc-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#b9b2a3" />
        </marker>
      </defs>
    </svg>
  );
}

// --- worked example ---------------------------------------------------------

function ExampleCard({ ex }) {
  if (!ex) return null;
  const d = DISPO[ex.disposition] || DISPO.review;
  return (
    <div className="sc-example" style={{ borderTopColor: d.color }}>
      <div className="sc-ex-head">
        <span className={`pill ${d.pill}`}>{ex.disposition}</span>
        <span className="sc-ex-score">score <b>{ex.risk_score ?? "—"}</b></span>
      </div>
      <div className="sc-ex-payee">{ex.payee || "(unnamed payee)"}</div>
      <div className="sc-ex-amount mono">{fmtAmount(ex.amount)}</div>

      {ex.matches && ex.matches.length > 0 ? (
        <div className="sc-ex-matches">
          {ex.matches.map((m, i) => (
            <div key={i} className="sc-ex-match">
              <span className="sc-ex-mtag" style={{ color: MATCH_COLOR[m.matched_on] || "var(--ink)" }}>
                {MATCH_LABEL[m.matched_on] || m.matched_on}
              </span>
              <span className="setdesc" style={{ margin: 0 }}>
                {m.source}
                {m.similarity != null ? ` · similarity ${m.similarity}` : ""}
                {m.confidence != null ? ` · conf ${m.confidence}` : ""}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="sc-ex-clean">No reference match — cleared to pay.</div>
      )}

      {ex.reasons && ex.reasons.length > 0 && (
        <ul className="sc-ex-reasons">
          {ex.reasons.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      )}
      <div className="sc-ex-foot mono">
        {ex.payment_id} · screened against list v{ex.reference_list_version ?? "—"}
      </div>
    </div>
  );
}

// --- page -------------------------------------------------------------------

export default function Showcase() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => { getShowcase().then(setData).catch((e) => setErr(String(e.message || e))); }, []);

  if (err) return <div className="body"><div className="verdict bad">Failed to load the showcase: {err}</div></div>;
  if (!data) return <div className="body"><div className="sub">Loading the live picture…</div></div>;

  const s = data.summary || {};
  const mix = s.disposition_mix || {};
  const total = s.total_screened || 0;

  return (
    <div className="showcase">
      {/* HERO */}
      <section className="sc-hero">
        <div className="sc-hero-inner">
          <span className="sc-kicker">U.S. Treasury · Do Not Pay model</span>
          <h1>PrePayGuard</h1>
          <p className="sc-lede">
            Every payment is screened for integrity <i>before</i> the money leaves. Improper
            payments are stopped or routed to a human, clean ones flow through, and every single
            decision is written to an audit record that can never be altered. This page is a live
            look at what the platform has actually done.
          </p>
          <div className="sc-hero-stats">
            <div className="sc-hs"><div className="sc-hs-v">{total}</div><div className="sc-hs-k">payments screened</div></div>
            <div className="sc-hs"><div className="sc-hs-v">{s.hit_rate ?? 0}%</div><div className="sc-hs-k">flagged for risk</div></div>
            <div className="sc-hs"><div className="sc-hs-v">{mix.reject || 0}</div><div className="sc-hs-k">stopped before payout</div></div>
            <div className="sc-hs"><div className="sc-hs-v">{s.queue?.pending ?? 0}</div><div className="sc-hs-k">awaiting a reviewer</div></div>
          </div>
        </div>
      </section>

      <div className="sc-wrap">
        {/* HOW IT WORKS */}
        <section className="sc-section">
          <h2 className="sc-h2">How a payment moves through the pipeline</h2>
          <p className="sc-p">
            The pipeline is five independent, queue-decoupled services. A payment is taken in and
            de-duplicated (A), matched against Do Not Pay reference sources (B), scored (C), and
            given a disposition (D). Whatever the outcome, an immutable audit record is written —
            and anything ambiguous is handed to a human reviewer rather than guessed at.
          </p>
          <div className="sc-flow-wrap"><PipelineFlow /></div>
        </section>

        {/* HOW IT DECIDES */}
        <section className="sc-section">
          <h2 className="sc-h2">How it decides — and why you can defend the decision</h2>
          <p className="sc-p">
            There is no black-box classifier. The risk score is a transparent, rule-based number,
            so every disposition can be explained line by line and reproduced exactly. The design
            is deliberately asymmetric: a payment is only rejected outright on a confirmed taxpayer
            ID match — the strongest possible evidence. Weaker name signals raise a flag but route
            to a human, because the cost of wrongly blocking a legitimate payee is real.
          </p>
          <div className="sc-decision-grid">
            <div className="sc-dcard" style={{ borderTopColor: "var(--green)" }}>
              <div className="sc-dband" style={{ color: "var(--green)" }}>Approve</div>
              <div className="sc-drange">score &lt; 30</div>
              <p>No meaningful match. The payment clears and is recorded.</p>
            </div>
            <div className="sc-dcard" style={{ borderTopColor: "var(--amber)" }}>
              <div className="sc-dband" style={{ color: "var(--amber)" }}>Review</div>
              <div className="sc-drange">score 30 – 79</div>
              <p>A name or semantic signal. A human adjudicates; the decision is itself audited.</p>
            </div>
            <div className="sc-dcard" style={{ borderTopColor: "var(--red)" }}>
              <div className="sc-dband" style={{ color: "var(--red)" }}>Reject</div>
              <div className="sc-drange">score ≥ 80</div>
              <p>A confirmed identity match. The payment is stopped before it can go out.</p>
            </div>
          </div>
        </section>

        {/* WHAT IT DID — LIVE METRICS */}
        <section className="sc-section">
          <h2 className="sc-h2">What it has done so far</h2>
          <p className="sc-p">Live figures, pulled the moment this page loaded.</p>
          <div className="sc-metrics">
            <div className="panel sc-metric">
              <h3>Disposition mix</h3>
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
            <div className="panel sc-metric">
              <h3>Risk hit rate</h3>
              <Gauge value={s.hit_rate} />
              <div className="setdesc" style={{ textAlign: "center" }}>
                Share of payments that carried enough risk to be flagged (review + reject).
              </div>
            </div>
            <div className="panel sc-metric sc-metric-wide">
              <h3>Throughput — last 14 days</h3>
              <Timeline data={s.throughput} />
            </div>
            <div className="panel sc-metric sc-metric-wide">
              <h3>What triggered the flag</h3>
              <MatchTypeBars matchTypes={data.match_types || {}} sample={data.match_sample_size || 0} />
            </div>
          </div>
        </section>

        {/* WORKED EXAMPLES */}
        <section className="sc-section">
          <h2 className="sc-h2">Three real decisions</h2>
          <p className="sc-p">
            Pulled straight from the audit log — one of each disposition, with the evidence and the
            exact reasons the pipeline recorded.
          </p>
          <div className="sc-examples">
            <ExampleCard ex={data.examples?.approve} />
            <ExampleCard ex={data.examples?.review} />
            <ExampleCard ex={data.examples?.reject} />
          </div>
        </section>

        {/* INTELLIGENCE */}
        <section className="sc-section">
          <h2 className="sc-h2">The intelligence behind the screen</h2>
          <div className="sc-two">
            <div className="panel">
              <h3>Semantic matching</h3>
              <p className="sc-p" style={{ marginBottom: 0 }}>
                String rules miss a payee that has been reworded. PrePayGuard embeds each reference
                name (Bedrock Titan) and compares by meaning, so a variant like
                {" "}<i>"Globex Overseas Incorporated"</i> is caught against a listed
                {" "}<i>"Globex Offshore Inc"</i> even though the text barely overlaps — then capped
                to human review rather than an automatic block. No vector database; the vectors live
                in the versioned reference document itself.
              </p>
            </div>
            <div className="panel">
              <h3>Advisory AI briefs</h3>
              <p className="sc-p" style={{ marginBottom: 0 }}>
                On demand, a reviewer can generate a plain-language brief (Bedrock Nova Lite) that
                summarizes the evidence and suggests an action. It is grounded strictly in the
                screening record — it invents nothing — and it is advisory only:
                {" "}<b>never written to the immutable audit</b>. The human makes and owns the call.
              </p>
            </div>
          </div>
        </section>

        {/* TRUST */}
        <section className="sc-section">
          <h2 className="sc-h2">Built for trust</h2>
          <div className="sc-trust">
            <div className="sc-tcard"><b>Immutable audit</b><span>Every disposition is written to S3 Object Lock (COMPLIANCE) with a SHA-256 hash. It cannot be edited or deleted by anyone — including the account root.</span></div>
            <div className="sc-tcard"><b>Segregation of duties</b><span>Whoever submits a payment cannot be the one who clears it. The control is enforced per payment, not by policy alone.</span></div>
            <div className="sc-tcard"><b>Four roles</b><span>Submitter, reviewer, admin, and a read-only auditor who can see everything and change nothing.</span></div>
            <div className="sc-tcard"><b>Versioned lists</b><span>Every screening cites the exact reference-list version it was judged against, so "what said so?" is answerable forever.</span></div>
          </div>
        </section>
      </div>
    </div>
  );
}
