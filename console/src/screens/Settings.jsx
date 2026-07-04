import { useState } from "react";
import { resetData } from "../lib/api.js";

export default function Settings({ settings, onChange, isAdmin }) {
  const [saved, setSaved] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [reset, setReset] = useState(null); // null | "working" | {cleared,total} | {error}
  const upd = (patch) => { onChange(patch); setSaved(true); setTimeout(() => setSaved(false), 1500); };

  const doReset = async () => {
    setReset("working");
    try {
      const r = await resetData();
      setReset(r);
      setConfirmText("");
    } catch (e) {
      setReset({ error: String(e.message || e) });
    }
  };

  return (
    <div className="body">
      <h2>Settings {saved && <span className="saved">saved ✓</span>}</h2>
      <div className="sub">Preferences are saved to this browser.</div>

      <div className="panel" style={{ maxWidth: 640 }}>
        <h3>Appearance</h3>
        <div className="setrow">
          <div><b>Density</b><div className="setdesc">Row and control spacing across the console.</div></div>
          <div className="radios">
            <label><input type="radio" name="density" checked={settings.density === "comfortable"}
              onChange={() => upd({ density: "comfortable" })} /> Comfortable</label>
            <label><input type="radio" name="density" checked={settings.density === "compact"}
              onChange={() => upd({ density: "compact" })} /> Compact</label>
          </div>
        </div>
      </div>

      <div className="panel" style={{ maxWidth: 640, marginTop: 14 }}>
        <h3>Review queue</h3>
        <div className="setrow">
          <div><b>Default filter</b><div className="setdesc">Which items show when you open the queue.</div></div>
          <select value={settings.defaultFilter} onChange={(e) => upd({ defaultFilter: e.target.value })}
            aria-label="Default filter">
            <option value="pending">Pending</option>
            <option value="all">All</option>
          </select>
        </div>
      </div>

      {isAdmin && (
        <div className="panel danger-panel" style={{ maxWidth: 640, marginTop: 14 }}>
          <h3>Demo controls</h3>
          <p className="setdesc" style={{ marginBottom: 12 }}>
            Clears the working data — the review queue, audit index, batch summaries, and
            idempotency store — so a demo starts from zero. The immutable audit records in
            S3 Object Lock are <b>not</b> affected: the dashboards read empty, but every
            historical disposition stays permanently locked in the audit bucket.
          </p>
          <div className="setrow" style={{ borderBottom: 0, alignItems: "flex-start" }}>
            <div>
              <b>Clear all working data</b>
              <div className="setdesc">Type <code>RESET</code> to enable. This cannot be undone.</div>
              <input value={confirmText} onChange={(e) => setConfirmText(e.target.value)}
                placeholder="RESET" aria-label="Reset confirmation"
                style={{ marginTop: 8, padding: "7px 10px", border: "1px solid var(--line)", borderRadius: 5, font: "14px var(--mono)", width: 160 }} />
            </div>
            <button className="btn btn-red" disabled={confirmText !== "RESET" || reset === "working"}
              onClick={doReset}>
              {reset === "working" ? "Clearing…" : "Clear data"}
            </button>
          </div>
          {reset && reset !== "working" && !reset.error && (
            <div className="verdict ok" data-testid="reset-result">
              Cleared {reset.total} records. Dashboards now read zero — the immutable audit is untouched.
            </div>
          )}
          {reset?.error && <div className="verdict bad">Reset failed: {reset.error}</div>}
        </div>
      )}
    </div>
  );
}
