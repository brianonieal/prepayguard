import { useEffect, useState } from "react";
import { getShowcase } from "../lib/api.js";
import Showcase from "./Showcase.jsx";

// The single "what's happening" surface: a flagged-item hero (the reason the tool
// exists) on top of the executive Overview. Merges the old Overview tab; the audit
// log + export live in the Audit log tab (canAnalytics).
export default function Dashboard({ onNav }) {
  const [pending, setPending] = useState(null);
  useEffect(() => { getShowcase().then((d) => setPending(d.summary?.queue?.pending ?? 0)).catch(() => setPending(0)); }, []);

  return (
    <>
      {pending > 0 && (
        <div className="body" style={{ paddingBottom: 0 }}>
          <div className="result-ok" data-testid="flag-hero"
            style={{ display: "flex", alignItems: "center", gap: 14, borderLeftColor: "var(--amber)", background: "#fdf6e3" }}>
            <b style={{ fontSize: 18 }}>{pending}</b>
            <span>payment{pending === 1 ? "" : "s"} awaiting human review.</span>
            <button className="btn btn-primary btn-sm" style={{ marginLeft: "auto" }} onClick={() => onNav("#/reviews")}>
              Go to review queue →
            </button>
          </div>
        </div>
      )}
      <Showcase />
    </>
  );
}
