import { useEffect, useState } from "react";
import { getReference, putReference, listReferenceVersions, getReferenceVersion } from "../lib/api.js";

const SEVERITIES = ["high", "medium", "low"];
const BLANK = { name: "", tin: "", source: "", severity: "high" };

export default function ReferenceData() {
  const [doc, setDoc] = useState(null);        // current published doc
  const [entries, setEntries] = useState([]);  // editable working copy
  const [versions, setVersions] = useState([]);
  const [viewing, setViewing] = useState(null); // an older version being inspected
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const load = () => {
    getReference().then((d) => { setDoc(d); setEntries(d.entries.map((e) => ({ ...e }))); })
      .catch((e) => setErr(String(e.message || e)));
    listReferenceVersions().then((d) => setVersions(d.versions || [])).catch(() => {});
  };
  useEffect(load, []);

  if (err && !doc) return <div className="body"><div className="verdict bad">Failed to load reference data: {err}</div></div>;
  if (!doc) return <div className="body"><div className="sub">Loading reference data…</div></div>;

  const set = (i, k) => (e) => setEntries((prev) => {
    const next = [...prev];
    next[i] = { ...next[i], [k]: e.target.value };
    return next;
  });
  const remove = (i) => setEntries((prev) => prev.filter((_, j) => j !== i));
  const dirty = JSON.stringify(entries) !== JSON.stringify(doc.entries);

  const publish = async () => {
    setBusy(true); setErr(""); setMsg("");
    try {
      const r = await putReference({ entries, sources: doc.sources });
      setMsg(`Published version ${r.version} (${r.entry_count} entries). Screening picks it up within ~60s.`);
      setViewing(null);
      load();
    } catch (ex) {
      setErr(String(ex?.message || "publish failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="body">
      <h2>Reference data</h2>
      <div className="sub">
        The Do Not Pay screening lists. Publishing creates an immutable new version;
        every screening decision cites the version it matched against.
      </div>

      <div className="stats">
        <div className="stat"><div className="k">Active version</div><div className="v">v{doc.version}</div><div className="d">what enrichment screens against</div></div>
        <div className="stat"><div className="k">Entries</div><div className="v">{entries.length}</div><div className="d">{doc.entries.length} published{dirty ? " · unpublished edits" : ""}</div></div>
        <div className="stat"><div className="k">Last published</div><div className="v" style={{ fontSize: 15 }}>{(doc.updated_at || "").slice(0, 10) || "-"}</div><div className="d mono" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{doc.updated_by}</div></div>
      </div>

      {msg && <div className="result-ok" style={{ marginTop: 0 }}>{msg}</div>}
      {err && <div className="verdict bad">{err}</div>}

      <div className="detail-grid">
        <div className="panel">
          <h3>Entries (working copy)</h3>
          <table>
            <thead><tr><th>Name</th><th>TIN</th><th>Source</th><th>Severity</th><th></th></tr></thead>
            <tbody>
              {entries.map((e, i) => (
                <tr key={i}>
                  <td><input aria-label={`entry ${i} name`} value={e.name} onChange={set(i, "name")} /></td>
                  <td><input aria-label={`entry ${i} tin`} className="mono" value={e.tin || ""} onChange={set(i, "tin")} style={{ maxWidth: 120 }} /></td>
                  <td><input aria-label={`entry ${i} source`} value={e.source} onChange={set(i, "source")} /></td>
                  <td>
                    <select aria-label={`entry ${i} severity`} value={e.severity} onChange={set(i, "severity")}>
                      {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td><button className="rowlink" onClick={() => remove(i)} aria-label={`remove entry ${i}`}>remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: 12, display: "flex", gap: 10 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setEntries((p) => [...p, { ...BLANK }])}>+ Add entry</button>
            <button className="btn btn-primary btn-sm" disabled={busy || !dirty || entries.length === 0} onClick={publish}>
              {busy ? "Publishing…" : `Publish new version (v${doc.version + 1})`}
            </button>
          </div>
          <div className="note" style={{ maxWidth: "none", marginTop: 12 }}>
            Publishing never edits history: v{doc.version} stays retrievable forever, and audit
            records that cite it keep meaning exactly what they meant.
          </div>
        </div>

        <div className="panel">
          <h3>Version history</h3>
          {versions.length === 0 && <div className="sub" style={{ margin: 0 }}>No versions yet.</div>}
          <dl>
            {versions.map((v) => (
              <div key={v.version} style={{ display: "flex", gap: 8, alignItems: "baseline", marginBottom: 6 }}>
                <span className={`pill ${v.version === doc.version ? "p-approved" : "p-pending"}`}>v{v.version}</span>
                <span className="mono" style={{ fontSize: 12 }}>{v.published_at.slice(0, 10)}</span>
                <button className="rowlink" onClick={() => getReferenceVersion(v.version).then(setViewing).catch(() => {})}>view</button>
              </div>
            ))}
          </dl>
          {viewing && (
            <div style={{ marginTop: 10 }}>
              <div className="sub" style={{ marginBottom: 6 }}>
                <b>v{viewing.version}</b> · {viewing.entries.length} entries · {viewing.updated_by}
              </div>
              <table>
                <thead><tr><th>Name</th><th>TIN</th><th>Source</th><th>Sev</th></tr></thead>
                <tbody>
                  {viewing.entries.map((e, i) => (
                    <tr key={i}><td>{e.name}</td><td className="mono">{e.tin || "-"}</td><td>{e.source}</td><td>{e.severity}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
