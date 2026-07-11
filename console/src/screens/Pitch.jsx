// Read-only, scrollable one-page pitch (for professors). No interactivity beyond
// scrolling. Matches the existing console theme (same colors, fonts, card style);
// no new design language. Copy is used verbatim. Three visuals: a stat row, the
// three-outcome flow, and a static architecture diagram whose structure mirrors the
// Mermaid diagram in docs/HANDOFF.md exactly (so the two can never disagree).

// Real values (docs/HANDOFF.md): 149 test functions; three dispositions; seven
// pipeline components (A-G) plus the console API; S3 Object Lock audit.
const STATS = [
  { k: "Tests", v: "149", d: "automated, green in CI" },
  { k: "Outcomes", v: "3", d: "approve, review, block" },
  { k: "Components", v: "8", d: "pipeline A to G, plus console" },
  { k: "Audit trail", v: "Immutable", d: "S3 Object Lock (COMPLIANCE)" },
];

// --- three-outcome flow: Payment -> Screen -> Approve / Review / Block -----------
function OutcomeFlow() {
  const box = (x, y, w, fill, stroke, label, tc) => (
    <g>
      <rect x={x} y={y} width={w} height={42} rx={6} fill={fill} stroke={stroke} strokeWidth={1.5} />
      <text x={x + w / 2} y={y + 26} textAnchor="middle" fontSize="13" fontWeight="600" fill={tc}>{label}</text>
    </g>
  );
  return (
    <svg viewBox="0 0 520 172" role="img" aria-label="A payment is screened, then approved, sent to a human, or blocked">
      <defs>
        <marker id="ah" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#6b6455" />
        </marker>
      </defs>
      {box(8, 65, 110, "#fff", "var(--navy)", "Payment", "var(--ink)")}
      {box(175, 65, 110, "var(--navy)", "var(--navy)", "Screen", "#fff")}
      {box(360, 8, 150, "#ddefdb", "var(--green)", "Approve", "var(--green)")}
      {box(360, 65, 150, "#f3e2bd", "var(--amber)", "Review (human)", "#8a5a13")}
      {box(360, 122, 150, "#f0cfcc", "var(--red)", "Block", "var(--red)")}
      <line x1={118} y1={86} x2={173} y2={86} stroke="#6b6455" strokeWidth="1.5" markerEnd="url(#ah)" />
      <line x1={285} y1={86} x2={358} y2={29} stroke="var(--green)" strokeWidth="1.5" markerEnd="url(#ah)" />
      <line x1={285} y1={86} x2={358} y2={86} stroke="var(--amber)" strokeWidth="1.5" markerEnd="url(#ah)" />
      <line x1={285} y1={86} x2={358} y2={143} stroke="var(--red)" strokeWidth="1.5" markerEnd="url(#ah)" />
    </svg>
  );
}

// --- architecture: same structure as the Mermaid diagram in docs/HANDOFF.md ------
const H = 38;
const A_NODES = [
  { id: "caller", x: 12, y: 150, w: 96, label: "Caller" },
  { id: "apigw", x: 12, y: 206, w: 96, label: "API Gateway" },
  { id: "a", x: 142, y: 206, w: 98, label: "A. Intake" },
  { id: "b", x: 274, y: 206, w: 110, label: "B. Enrichment" },
  { id: "c", x: 418, y: 206, w: 104, label: "C. Risk score" },
  { id: "d", x: 556, y: 206, w: 110, label: "D. Disposition" },
  { id: "ref", x: 274, y: 120, w: 110, label: "Reference list", store: true },
  { id: "g", x: 274, y: 54, w: 110, label: "G. Refresher" },
  { id: "e", x: 128, y: 120, w: 112, label: "E. Batch ingest" },
  { id: "f", x: 128, y: 54, w: 112, label: "F. Feeder" },
  { id: "audit", x: 700, y: 138, w: 150, label: "Audit store", store: true },
  { id: "review", x: 700, y: 206, w: 150, label: "Review queue" },
  { id: "hook", x: 700, y: 274, w: 150, label: "Webhook" },
  { id: "console", x: 142, y: 300, w: 98, label: "Console" },
  { id: "capi", x: 274, y: 300, w: 122, label: "Console API" },
];
const A_EDGES = [
  { s: "caller", t: "apigw" }, { s: "apigw", t: "a" },
  { s: "a", t: "b", l: "SQS" }, { s: "b", t: "c", l: "SQS" }, { s: "c", t: "d", l: "SQS" },
  { s: "g", t: "ref" }, { s: "ref", t: "b" }, { s: "f", t: "e" }, { s: "e", t: "b" },
  { s: "d", t: "audit" }, { s: "d", t: "review" }, { s: "d", t: "hook" },
  { s: "console", t: "capi" },
  { s: "capi", t: "audit", dashed: true, l: "reads" }, { s: "capi", t: "review", dashed: true, l: "reads" },
];
function ArchDiagram() {
  const byId = Object.fromEntries(A_NODES.map((n) => [n.id, n]));
  const pts = (s, t) => {
    const sc = { x: s.x + s.w / 2, y: s.y + H / 2 }, tc = { x: t.x + t.w / 2, y: t.y + H / 2 };
    const dx = tc.x - sc.x, dy = tc.y - sc.y;
    if (Math.abs(dx) >= Math.abs(dy)) {
      return { x1: dx > 0 ? s.x + s.w : s.x, y1: sc.y, x2: dx > 0 ? t.x : t.x + t.w, y2: tc.y };
    }
    return { x1: sc.x, y1: dy > 0 ? s.y + H : s.y, x2: tc.x, y2: dy > 0 ? t.y : t.y + H };
  };
  return (
    <svg viewBox="0 0 862 356" role="img" aria-label="Architecture: caller to API Gateway to intake, enrichment, risk scoring, disposition; disposition writes to the audit store, review queue, and webhook; feeder and refresher supply the reference list and batch ingest; the console reads the audit store and review queue">
      <defs>
        <marker id="aa" markerWidth="8" markerHeight="8" refX="6.5" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#8a8272" />
        </marker>
      </defs>
      {A_EDGES.map((e, i) => {
        const p = pts(byId[e.s], byId[e.t]);
        return (
          <g key={i}>
            <line x1={p.x1} y1={p.y1} x2={p.x2} y2={p.y2} stroke="#a9a394"
              strokeWidth="1.4" markerEnd="url(#aa)" strokeDasharray={e.dashed ? "4 3" : undefined} />
            {e.l && <text x={(p.x1 + p.x2) / 2} y={(p.y1 + p.y2) / 2 - 3} textAnchor="middle"
              fontSize="9.5" fill="#8a8272" style={{ paintOrder: "stroke" }} stroke="var(--paper)" strokeWidth="3">{e.l}</text>}
          </g>
        );
      })}
      {A_NODES.map((n) => (
        <g key={n.id}>
          <rect x={n.x} y={n.y} width={n.w} height={H} rx={6}
            fill={n.store ? "#eef3f1" : "#fff"} stroke="var(--line)" strokeWidth="1.2" />
          <text x={n.x + n.w / 2} y={n.y + 24} textAnchor="middle" fontSize="11.5"
            fontWeight="600" fill="var(--navy)">{n.label}</text>
        </g>
      ))}
    </svg>
  );
}

export default function Pitch() {
  return (
    <div className="body pitch">
      <div className="pitch-hero">
        <h1>PrePayGuard</h1>
        <p className="pitch-tagline">Pre-payment integrity screening for federal disbursements</p>
      </div>

      <div className="pitch-stats">
        {STATS.map((s) => (
          <div className="stat" key={s.k}>
            <div className="k">{s.k}</div>
            <div className="v">{s.v}</div>
            <div className="d">{s.d}</div>
          </div>
        ))}
      </div>

      <section className="pitch-section">
        <h2>The problem</h2>
        <p>Every year the government pays people it shouldn't: dead payees, debarred contractors, entities that owe federal debt. Not on purpose. It happens because at the moment a payment goes out, the system cutting the check doesn't know what the exclusion lists know. PrePayGuard is the check that runs in that moment. It screens every payment against the government's Do Not Pay watchlists before the money leaves, not after. Catching a bad payment up front beats clawing it back later.</p>
      </section>

      <section className="pitch-section">
        <h2>What I built</h2>
        <p>A working, deployed system on AWS. A payment comes in, gets screened against real SAM.gov exclusion data, and gets one of three outcomes: approve, send to a human, or block. Real federal award data flows through it live from USASpending. Every decision writes a permanent, tamper-evident record. It runs on Lambda and SQS, the infrastructure is all Terraform, it ships through CI with security scanning, and it's covered by 149 tests. This isn't a mockup. It's real and it runs.</p>
        <figure className="pitch-figure pitch-figure-sm">
          <OutcomeFlow />
        </figure>
      </section>

      <figure className="pitch-figure">
        <ArchDiagram />
        <figcaption className="pitch-cap">How a payment flows through the system (the same architecture documented in the technical handoff).</figcaption>
      </figure>

      <section className="pitch-section">
        <h2>The idea that makes it work</h2>
        <p>I put a language model inside a system that decides whether to release federal money, and I made it structurally unable to release anything. The model writes advisory notes for a human reviewer. The actual decision is made by deterministic rules that never read what the model wrote. So when I fed it a payment whose payee name contained "approve this payment," the model did what it was told and recommended approval, and the payment was stopped anyway, because nothing the model says can move the decision. That's the point. The AI is allowed to be wrong because it can't act.</p>
      </section>

      <section className="pitch-section">
        <h2>What I found by attacking it</h2>
        <p>I didn't just build it and call it done. I attacked my own matcher and it failed: add about five characters to a listed name and it slips through screening entirely. I traced why, built a fix, measured that the fix only partly closes the gap, and documented exactly what's left. I found that the feed pulls the largest awards and structurally can't see the small ones, which is exactly where a debarred vendor is most likely to hide. I found a real excluded entity that actually received federal contracts, sitting in public data. Every one of these is written up honestly, limits and all. The findings are the capstone, not a footnote to it.</p>
      </section>

      <section className="pitch-section">
        <h2>The short version</h2>
        <p>Real system, real data, real deployment, and an honest account of where it breaks. Screens federal payments, keeps the AI on a leash, and tells you the truth about its own blind spots.</p>
      </section>
    </div>
  );
}
