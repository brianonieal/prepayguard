import { useEffect, useState } from "react";
import { getFeedConfig, putFeedConfig, runFeed } from "../lib/api.js";

// USAspending award_type_codes grouped into friendly categories (mirrors the
// usaspending.gov download builder). The saved config stores the flat code list.
const CATEGORIES = [
  { key: "contracts", label: "Contracts", codes: ["A", "B", "C", "D"] },
  { key: "grants", label: "Grants", codes: ["02", "03", "04", "05"] },
  { key: "direct", label: "Direct Payments", codes: ["06", "10"] },
  { key: "loans", label: "Loans", codes: ["07", "08"] },
  { key: "other", label: "Other Financial Assistance", codes: ["09", "11"] },
];

const selFromCodes = (codes) => {
  const set = new Set(codes || []);
  const sel = {};
  for (const c of CATEGORIES) sel[c.key] = c.codes.every((x) => set.has(x));
  return sel;
};
const codesFromSel = (sel) => CATEGORIES.filter((c) => sel[c.key]).flatMap((c) => c.codes);

export default function Feed() {
  const [sel, setSel] = useState({});
  const [days, setDays] = useState(365);
  const [limit, setLimit] = useState(10);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState("");   // "save" | "run" | ""
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [lastRun, setLastRun] = useState(null);

  useEffect(() => {
    getFeedConfig().then(({ config }) => {
      setSel(selFromCodes(config.award_type_codes));
      setDays(config.time_period_days ?? 365);
      setLimit(config.limit ?? 10);
      setLoaded(true);
    }).catch((e) => setErr(String(e.message || e)));
  }, []);

  const cfg = () => ({ award_type_codes: codesFromSel(sel), time_period_days: Number(days), limit: Number(limit) });
  const noTypes = codesFromSel(sel).length === 0;

  const save = async () => {
    setBusy("save"); setErr(""); setMsg("");
    try {
      await putFeedConfig(cfg());
      setMsg("Saved. The scheduled feed will use these filters on its next run.");
    } catch (ex) { setErr(String(ex?.message || "save failed")); }
    finally { setBusy(""); }
  };

  const run = async () => {
    setBusy("run"); setErr(""); setMsg("");
    try {
      const r = await runFeed(cfg());
      setLastRun(r.result || {});
      setMsg(`Pulled now: ${r.result?.written ?? 0} payment(s) screened. They appear in the console shortly.`);
    } catch (ex) { setErr(String(ex?.message || "run failed")); }
    finally { setBusy(""); }
  };

  if (err && !loaded) return <div className="body"><div className="verdict bad">Failed to load feed config: {err}</div></div>;
  if (!loaded) return <div className="body"><div className="sub">Loading feed config…</div></div>;

  const toggle = (k) => setSel((p) => ({ ...p, [k]: !p[k] }));

  return (
    <div className="body">
      <h2>Feed</h2>
      <div className="sub">
        Configure the real federal data the feeder pulls from USAspending. Save sets what
        the scheduled feed uses; Run now pulls immediately with these filters. Each pull
        screens real payees and writes permanent audit records, bounded by the size below.
      </div>

      {msg && <div className="result-ok" style={{ marginTop: 0 }}>{msg}</div>}
      {err && <div className="verdict bad">{err}</div>}

      <div className="detail-grid">
        <div className="panel">
          <h3>Award types</h3>
          {CATEGORIES.map((c) => (
            <label key={c.key} style={{ display: "block", marginBottom: 6 }}>
              <input type="checkbox" aria-label={c.label} checked={!!sel[c.key]} onChange={() => toggle(c.key)} />{" "}
              {c.label}
            </label>
          ))}
          {noTypes && <div className="sub" style={{ color: "#b00", margin: "4px 0 0" }}>Pick at least one award type.</div>}
        </div>

        <div className="panel">
          <h3>Window and size</h3>
          <label style={{ display: "block", marginBottom: 10 }}>
            Look back (days)
            <input type="number" aria-label="days" min="1" max="3650" value={days}
              onChange={(e) => setDays(e.target.value)} style={{ display: "block", maxWidth: 140 }} />
          </label>
          <label style={{ display: "block", marginBottom: 10 }}>
            Payments per pull (max 100)
            <input type="number" aria-label="limit" min="1" max="100" value={limit}
              onChange={(e) => setLimit(e.target.value)} style={{ display: "block", maxWidth: 140 }} />
          </label>
          <div style={{ marginTop: 12, display: "flex", gap: 10 }}>
            <button className="btn btn-ghost btn-sm" disabled={!!busy || noTypes} onClick={save}>
              {busy === "save" ? "Saving…" : "Save"}
            </button>
            <button className="btn btn-primary btn-sm" disabled={!!busy || noTypes} onClick={run}>
              {busy === "run" ? "Pulling…" : "Run now"}
            </button>
          </div>
          {lastRun && (
            <div className="note" style={{ maxWidth: "none", marginTop: 12 }}>
              Last run: {lastRun.written ?? 0} written · source {lastRun.source || "usaspending"}.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
