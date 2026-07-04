import { useState } from "react";

export default function Settings({ settings, onChange }) {
  const [saved, setSaved] = useState(false);
  const upd = (patch) => { onChange(patch); setSaved(true); setTimeout(() => setSaved(false), 1500); };

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
        <h3>Notifications</h3>
        <div className="setrow">
          <div><b>Email digest</b><div className="setdesc">Daily summary of pending reviews.</div></div>
          <label className="switch"><input type="checkbox" checked={settings.emailDigest}
            onChange={(e) => upd({ emailDigest: e.target.checked })} aria-label="Email digest" /><span /></label>
        </div>
        <div className="setrow">
          <div><b>Review assignment alerts</b><div className="setdesc">When a case is assigned to you.</div></div>
          <label className="switch"><input type="checkbox" checked={settings.assignAlerts}
            onChange={(e) => upd({ assignAlerts: e.target.checked })} aria-label="Assignment alerts" /><span /></label>
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
    </div>
  );
}
