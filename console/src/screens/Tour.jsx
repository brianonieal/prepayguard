import { useState } from "react";

// A clickable, plain-English walkthrough of what PrePayGuard does and how to use it.
// Semi-casual, semi-professional. Each step can deep-link to the real screen it
// describes ("Take me there"); role-gated links only show when the viewer can follow
// them. Written for someone who has never seen the tool before.
const STEPS = [
  {
    icon: "🛡️",
    title: "What PrePayGuard actually does",
    body: "Here's the whole idea in one line: check every payment against the government's Do Not Pay watchlists before the money goes out, not after. Catching a bad payment up front beats clawing it back later. This tour takes about two minutes.",
  },
  {
    icon: "📊",
    title: "Your dashboard, at a glance",
    body: "The dashboard is your live scoreboard: how many payments got checked, how many were flagged, how many were stopped automatically, and how many are waiting on a human. It refreshes every time you open it, so you always know where things stand.",
    cta: { label: "Show me the dashboard", hash: "#/dashboard", need: "review" },
  },
  {
    icon: "🎯",
    title: "Decisions you can actually explain",
    body: "Every payment gets a risk score from a plain points system, not a black-box AI. A clean payment approves itself, an obvious bad one gets stopped, and anything in between comes to a person. Because it is just rules, you can always explain exactly why a payment landed where it did.",
  },
  {
    icon: "🧑‍⚖️",
    title: "The review queue is your worklist",
    body: "When the engine is not sure (a risk score between 30 and 79), the payment lands here for a human call. Search it, filter it, and clear cases one at a time or in bulk. An oldest-pending clock keeps anything from quietly slipping through.",
    cta: { label: "Open the review queue", hash: "#/reviews", need: "review" },
  },
  {
    icon: "🔍",
    title: "See exactly why something was flagged",
    body: "Open any case and you get the receipts: which name or taxpayer ID matched, on which list, how confident, and the exact math behind the score (raw, then weighted, then capped). No guessing about why a payment needs a look.",
  },
  {
    icon: "🤖",
    title: "An AI brief, when you want a second read",
    body: "Need a quick summary before you decide? Ask for an AI brief, a plain-English readout of the case. It is advisory only: it never makes the decision, and it never becomes part of the official record. You are always the one who calls it.",
  },
  {
    icon: "🔒",
    title: "A record no one can quietly change",
    body: "Every decision is written to tamper-proof storage the moment it is made, with a fingerprint (a SHA-256 hash) attached. You can re-check that fingerprint right in your browser, so “has this record been altered?” is a question you can answer yourself, not take on faith.",
  },
  {
    icon: "🔄",
    title: "Keeping the watchlist and the feed current",
    body: "Admins keep the engine fed from inside the console: publish new versions of the Do Not Pay watchlist, and tune the automated feed that pulls in real federal payments to screen. Every check records exactly which watchlist version it used.",
    cta: { label: "Go to Admin", hash: "#/admin", need: "admin" },
  },
];

export default function Tour({ onNav, canReview = false, isAdmin = false }) {
  const [i, setI] = useState(0);
  const allow = (need) => need === "admin" ? isAdmin : need === "review" ? canReview : true;

  const last = i === STEPS.length - 1;
  const step = STEPS[i];
  const cta = step.cta && allow(step.cta.need) ? step.cta : null;

  return (
    <div className="body tour">
      <div className="tour-top">
        <h2>Tour of PrePayGuard</h2>
        <span className="tour-count">{i + 1} of {STEPS.length}</span>
      </div>
      <div className="tour-progress"><span style={{ width: `${Math.round(100 * (i + 1) / STEPS.length)}%` }} /></div>

      <div className="tour-card">
        <div className="tour-icon" aria-hidden="true">{step.icon}</div>
        <h3 className="tour-title">{step.title}</h3>
        <p className="tour-body">{step.body}</p>
        {cta && (
          <button className="btn btn-ghost btn-sm tour-cta" onClick={() => onNav(cta.hash)}>{cta.label} →</button>
        )}
      </div>

      <div className="tour-dots">
        {STEPS.map((s, n) => (
          <button key={n} className={`tour-dot ${n === i ? "on" : ""}`} aria-label={`Step ${n + 1}`} onClick={() => setI(n)} />
        ))}
      </div>

      <div className="tour-nav">
        <button className="btn btn-ghost btn-sm" disabled={i === 0} onClick={() => setI((n) => Math.max(0, n - 1))}>← Back</button>
        {last ? (
          <button className="btn btn-primary btn-sm" onClick={() => onNav(canReview ? "#/dashboard" : "#/tour")}>
            {canReview ? "Finish, go to dashboard →" : "Finish"}
          </button>
        ) : (
          <button className="btn btn-primary btn-sm" onClick={() => setI((n) => Math.min(STEPS.length - 1, n + 1))}>Next →</button>
        )}
      </div>
    </div>
  );
}
