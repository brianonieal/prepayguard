import { useEffect, useState } from "react";
import { getShowcase } from "../lib/api.js";

// v3.0.0 Executive Showcase, condensed + plain-English pass (v3.2.x).
// Live data, hand-built SVG charts, no chart library, and no em dashes anywhere.

const DISPO = {
  approve: { label: "Approve", color: "var(--green)", pill: "p-approved" },
  review: { label: "Review", color: "var(--amber)", pill: "p-pending" },
  reject: { label: "Reject", color: "var(--red)", pill: "p-rejected" },
};

// Plain-English names for the reference sources (the government watchlists).
const SOURCE_LABEL = {
  sam_exclusions: "SAM debarment list",
  death_master_file: "Social Security death records",
  treasury_offset: "Treasury delinquent-debt list",
  oig_leie: "OIG healthcare exclusion list",
};
const sourceLabel = (s) => SOURCE_LABEL[s] || String(s || "").replace(/_/g, " ");

// Plain-English names for the match types, for the "why it was flagged" chart.
const FLAG_LABEL = {
  tin: "Taxpayer ID match",
  name_exact: "Exact name match",
  name_fuzzy: "Close name match",
  name_semantic: "Similar-meaning match",
  none: "No match (cleared)",
};
const FLAG_ORDER = ["tin", "name_exact", "name_fuzzy", "name_semantic", "none"];
const FLAG_COLOR = {
  tin: "var(--red)", name_exact: "var(--navy)", name_fuzzy: "var(--amber)",
  name_semantic: "var(--copper)", none: "#c7c2b6",
};

function fmtAmount(a) {
  const n = Number(a);
  return Number.isFinite(n)
    ? n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 })
    : String(a ?? "");
}

// A plain-English sentence for one match, used in the worked examples.
function matchSentence(m) {
  const kind = {
    tin: "Taxpayer ID exactly matches",
    name_exact: "Exact name match on",
    name_fuzzy: "Close name match on",
    name_semantic: "Similar-meaning name match on",
  }[m.matched_on] || "Match on";
  const conf = m.confidence != null ? ` (${m.confidence}% confident)` : "";
  return `${kind} the ${sourceLabel(m.source)}${conf}`;
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
    <svg viewBox="0 0 140 140" className="sc-donut" role="img" aria-label="Outcome mix">
      <g transform="rotate(-90 70 70)">
        <circle cx="70" cy="70" r={r} fill="none" stroke="#ece8df" strokeWidth="17" />
        {segs.filter((s) => s.len > 0.5).map((s) => (
          <circle key={s.d} cx="70" cy="70" r={r} fill="none" stroke={DISPO[s.d].color}
            strokeWidth="17" strokeDasharray={`${s.len} ${C - s.len}`} strokeDashoffset={-s.offset} />
        ))}
      </g>
      <text x="70" y="66" textAnchor="middle" className="sc-donut-num">{total}</text>
      <text x="70" y="85" textAnchor="middle" className="sc-donut-lbl">checked</text>
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
    <svg viewBox="0 0 140 92" className="sc-gauge" role="img" aria-label={`Flagged rate ${v} percent`}>
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke="#ece8df" strokeWidth="13" strokeLinecap="round" />
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 ${big} 1 ${x} ${y}`} fill="none" stroke="var(--amber)" strokeWidth="13" strokeLinecap="round" />
      <text x={cx} y={cy - 6} textAnchor="middle" className="sc-donut-num">{v}%</text>
      <text x={cx} y={cy + 10} textAnchor="middle" className="sc-donut-lbl">flagged</text>
    </svg>
  );
}

function FlagBars({ matchTypes, sample }) {
  const rows = FLAG_ORDER.filter((k) => (matchTypes[k] || 0) > 0).map((k) => ({ k, n: matchTypes[k] }));
  if (!rows.length) return <div className="sub" style={{ margin: 0 }}>No payments checked yet.</div>;
  const max = Math.max(...rows.map((r) => r.n));
  return (
    <div className="sc-mtbars">
      {rows.map((r) => (
        <div key={r.k} className="sc-mtrow">
          <span className="sc-mtlabel">{FLAG_LABEL[r.k] || r.k}</span>
          <span className="sc-mttrack">
            <span className="sc-mtfill" style={{ width: `${Math.round(100 * r.n / max)}%`, background: FLAG_COLOR[r.k] }} />
          </span>
          <span className="sc-mtnum mono">{r.n}</span>
        </div>
      ))}
      <div className="setdesc" style={{ marginTop: 8 }}>
        Based on the {sample} most recent payments (the strongest signal found on each).
      </div>
    </div>
  );
}

function PipelineFlow() {
  const stages = [
    ["A", "Intake", "de-duplicated"],
    ["B", "Screening", "name and ID checks"],
    ["C", "Risk score", "plain, rule-based"],
    ["D", "Decision", "pay, review, or stop"],
  ];
  const NW = 150, NH = 62, GAP = 34, x0 = 10, y = 20;
  const totalW = x0 + stages.length * NW + (stages.length - 1) * GAP + 30;
  return (
    <svg viewBox={`0 0 ${totalW} 176`} className="sc-flow" role="img" aria-label="How a payment flows">
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
      {(() => {
        const dx = x0 + 3 * (NW + GAP);
        const auditY = y + NH + 42;
        return (
          <g>
            <line x1={dx + NW / 2} y1={y + NH} x2={dx + NW / 2} y2={auditY} stroke="#b9b2a3" strokeWidth="2" markerEnd="url(#sc-arrow)" />
            <rect x={dx} y={auditY} width={NW} height={NH} rx="8" fill="var(--navy)" />
            <text x={dx + NW / 2} y={auditY + 25} textAnchor="middle" className="sc-flow-name" fill="#fff">Permanent record</text>
            <text x={dx + NW / 2} y={auditY + 43} textAnchor="middle" className="sc-flow-sub" fill="#adc0d6">locked, tamper-proof</text>
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
        <span className="sc-ex-score">risk score <b>{ex.risk_score ?? 0}</b></span>
      </div>
      <div className="sc-ex-payee">{ex.payee || "(unnamed payee)"}</div>
      <div className="sc-ex-amount mono">{fmtAmount(ex.amount)}</div>

      {ex.matches && ex.matches.length > 0 ? (
        <ul className="sc-ex-reasons">
          {ex.matches.map((m, i) => <li key={i}>{matchSentence(m)}.</li>)}
        </ul>
      ) : (
        <div className="sc-ex-clean">No match on any government list. Cleared to pay.</div>
      )}
      <div className="sc-ex-foot mono">
        {ex.payment_id} · checked against reference list v{ex.reference_list_version ?? "?"}
      </div>
    </div>
  );
}

// --- page -------------------------------------------------------------------

export default function Showcase() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => { getShowcase().then(setData).catch((e) => setErr(String(e.message || e))); }, []);

  if (err) return <div className="body"><div className="verdict bad">Could not load the overview: {err}</div></div>;
  if (!data) return <div className="body"><div className="sub">Loading the live picture...</div></div>;

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
            Every payment is checked against official government watchlists <i>before</i> the money
            goes out. Risky payments are stopped or sent to a person, clean ones are paid, and every
            decision is saved to a permanent record that no one can change. Below is a live look at
            what the system has actually done.
          </p>
          <div className="sc-hero-stats">
            <div className="sc-hs"><div className="sc-hs-v">{total}</div><div className="sc-hs-k">payments checked</div></div>
            <div className="sc-hs"><div className="sc-hs-v">{s.hit_rate ?? 0}%</div><div className="sc-hs-k">flagged for risk</div></div>
            <div className="sc-hs"><div className="sc-hs-v">{mix.reject || 0}</div><div className="sc-hs-k">stopped before payout</div></div>
            <div className="sc-hs"><div className="sc-hs-v">{s.queue?.pending ?? 0}</div><div className="sc-hs-k">waiting on a person</div></div>
          </div>
        </div>
      </section>

      <div className="sc-wrap">
        {/* HOW IT WORKS */}
        <section className="sc-section">
          <h2 className="sc-h2">How a payment moves through the system</h2>
          <p className="sc-p">
            Five small, independent steps do the work. A payment comes in and is de-duplicated (A),
            checked against the watchlists (B), scored for risk (C), and given a decision (D).
            Whatever the outcome, a permanent record is saved. Anything unclear is handed to a person
            instead of being guessed at.
          </p>
          <div className="sc-flow-wrap"><PipelineFlow /></div>
        </section>

        {/* HOW IT DECIDES (expanded, plain) */}
        <section className="sc-section">
          <h2 className="sc-h2">How it decides, and why the decision holds up</h2>
          <p className="sc-p">
            Every payee is checked two ways: their <b>name</b> and their <b>taxpayer ID number</b>
            {" "}are compared against official U.S. government lists. Those lists cover companies barred
            from federal contracts, people and businesses that owe the government, and records of
            people who have died. The system adds up the strength of any matches into a single
            <b> risk score</b>.
          </p>
          <p className="sc-p">
            There is no black box. The score is a set of plain, published rules, so every decision can
            be explained line by line and repeated exactly. The rules lean toward caution in one
            direction only: a payment is stopped outright <b>only</b> on the strongest possible
            evidence, a confirmed taxpayer ID match. A weaker name-only match never stops a payment on
            its own. It sends the payment to a person, because wrongly blocking a legitimate payment is
            itself a real harm.
          </p>
          <div className="sc-decision-grid">
            <div className="sc-dcard" style={{ borderTopColor: "var(--green)" }}>
              <div className="sc-dband" style={{ color: "var(--green)" }}>Approve, and pay</div>
              <div className="sc-drange">risk score under 30</div>
              <p>No real match on any list. The payment is cleared, paid, and recorded.</p>
              <p className="sc-dex">For example, a vendor whose name and ID appear on none of the lists.</p>
            </div>
            <div className="sc-dcard" style={{ borderTopColor: "var(--amber)" }}>
              <div className="sc-dband" style={{ color: "var(--amber)" }}>Send to a person</div>
              <div className="sc-drange">risk score 30 to 79</div>
              <p>A name match, or a close or similar-sounding name, but no ID match. A person reviews it and decides, and that decision is recorded too.</p>
              <p className="sc-dex">For example, a payee whose name closely resembles one on a list.</p>
            </div>
            <div className="sc-dcard" style={{ borderTopColor: "var(--red)" }}>
              <div className="sc-dband" style={{ color: "var(--red)" }}>Stop the payment</div>
              <div className="sc-drange">risk score 80 or higher</div>
              <p>A confirmed taxpayer ID match on a watchlist, the strongest evidence. The payment is stopped before any money leaves.</p>
              <p className="sc-dex">For example, an ID that exactly matches a barred vendor.</p>
            </div>
          </div>
        </section>

        {/* WHAT IT HAS FOUND (donut + gauge + flag reasons; no throughput) */}
        <section className="sc-section">
          <h2 className="sc-h2">What it has found so far</h2>
          <p className="sc-p">Live figures, pulled the moment this page loaded.</p>
          <div className="sc-metrics">
            <div className="panel sc-metric">
              <h3>Outcomes</h3>
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
              <h3>Flagged for risk</h3>
              <Gauge value={s.hit_rate} />
              <div className="setdesc" style={{ textAlign: "center" }}>
                Share of payments risky enough to be stopped or sent to a person.
              </div>
            </div>
            <div className="panel sc-metric sc-metric-wide">
              <h3>Why payments were flagged</h3>
              <FlagBars matchTypes={data.match_types || {}} sample={data.match_sample_size || 0} />
            </div>
          </div>
        </section>

        {/* WORKED EXAMPLES (plain evidence) */}
        <section className="sc-section">
          <h2 className="sc-h2">Three real decisions</h2>
          <p className="sc-p">
            Taken straight from the permanent record, one of each outcome, with the exact evidence the
            system found.
          </p>
          <div className="sc-examples">
            <ExampleCard ex={data.examples?.approve} />
            <ExampleCard ex={data.examples?.review} />
            <ExampleCard ex={data.examples?.reject} />
          </div>
        </section>

        {/* THE CHECKS BEHIND IT (folded into one block, plain) */}
        <section className="sc-section">
          <h2 className="sc-h2">The checks behind the screening</h2>
          <div className="panel">
            <p className="sc-p" style={{ marginBottom: 10 }}>
              Two extra layers make the screening smarter. First, the system compares names by
              <b> meaning</b>, not just spelling, so a reworded payee like <i>"Globex Overseas
              Incorporated"</i> is still caught against a listed <i>"Globex Offshore Inc"</i>. A match
              like that never stops a payment on its own; it is always sent to a person.
            </p>
            <p className="sc-p" style={{ marginBottom: 0 }}>
              Second, a reviewer can ask for a short plain-language summary of the evidence and a
              suggested action, written by an AI assistant. That summary is <b>advisory only</b> and is
              never added to the permanent record. A person always makes and owns the final call.
            </p>
          </div>
        </section>

        {/* TRUST */}
        <section className="sc-section">
          <h2 className="sc-h2">Built for trust</h2>
          <div className="sc-trust">
            <div className="sc-tcard"><b>Records cannot be changed</b><span>Every decision is written to locked storage. It cannot be edited or deleted by anyone, including the people who run the system.</span></div>
            <div className="sc-tcard"><b>Separation of duties</b><span>The person who submits a payment can never be the one who approves it. This is enforced on every single payment.</span></div>
            <div className="sc-tcard"><b>Four roles</b><span>Submitter, reviewer, admin, and a read-only auditor who can see everything and change nothing.</span></div>
            <div className="sc-tcard"><b>Versioned watchlists</b><span>Every check records exactly which version of the lists it used, so "what did it match, and when?" can always be answered.</span></div>
          </div>
        </section>
      </div>
    </div>
  );
}
