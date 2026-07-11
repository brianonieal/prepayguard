import { useEffect, useState } from "react";
import { getReference, putReference, listReferenceVersions, getReferenceVersion } from "../lib/api.js";
import { useNameMasker } from "../lib/pii.js";

const SEVERITIES = ["high", "medium", "low"];
const BLANK = { name: "", tin: "", source: "", severity: "high" };

// The reference sources: plain-English names + whether the data is REAL (public
// government data) or a SYNTHETIC fixture (not publicly obtainable). Ordered real-first.
const SOURCE_META = {
  sam_exclusions: { label: "SAM.gov exclusions", sub: "GSA federal debarment list", real: true },
  oig_leie: { label: "HHS-OIG LEIE", sub: "excluded health-care providers", real: true },
  death_master_file: { label: "SSA Death Master File", sub: "not publicly obtainable", real: false },
  treasury_offset: { label: "Treasury Offset Program", sub: "not publicly obtainable", real: false },
};
const SOURCE_ORDER = ["sam_exclusions", "oig_leie", "death_master_file", "treasury_offset"];

export default function ReferenceData() {
  const [doc, setDoc] = useState(null);        // current published doc
  const [entries, setEntries] = useState([]);  // editable working copy
  const [versions, setVersions] = useState([]);
  const [viewing, setViewing] = useState(null); // an older version being inspected
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [selected, setSelected] = useState(new Set()); // row indices selected for bulk delete
  const { mask, isIndividual } = useNameMasker();

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
  const remove = (i) => { setEntries((prev) => prev.filter((_, j) => j !== i)); setSelected(new Set()); };
  const dirty = JSON.stringify(entries) !== JSON.stringify(doc.entries);

  // Multi-select → bulk delete. Edits the working copy; Publish persists a new
  // immutable version (same model as single remove / add / field edits).
  const toggleSel = (i) => setSelected((prev) => {
    const n = new Set(prev);
    n.has(i) ? n.delete(i) : n.add(i);
    return n;
  });
  const allSelected = entries.length > 0 && entries.every((_, i) => selected.has(i));
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(entries.map((_, i) => i)));
  const deleteSelected = () => { setEntries((prev) => prev.filter((_, i) => !selected.has(i))); setSelected(new Set()); };
  const addEntry = () => { setEntries((p) => [...p, { ...BLANK }]); setSelected(new Set()); };

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

  const sourceCounts = entries.reduce((m, e) => { const s = e.source || "(unset)"; m[s] = (m[s] || 0) + 1; return m; }, {});
  const shownSources = [...SOURCE_ORDER.filter((s) => sourceCounts[s]),
                        ...Object.keys(sourceCounts).filter((s) => !SOURCE_ORDER.includes(s))];

  return (
    <div className="body">
      <h2>Reference data</h2>
      <div className="sub">
        The Do Not Pay screening lists. Publishing creates an immutable new version;
        every screening decision cites the version it matched against.
      </div>

      <div className="ref-sources panel" aria-label="Data sources">
        <h3>Data sources</h3>
        <div className="ref-src-list">
          {shownSources.map((s) => {
            const m = SOURCE_META[s] || { label: s, sub: "", real: false };
            return (
              <div className="ref-src" key={s}>
                <span className={`src-tag ${m.real ? "real" : "synth"}`}>{m.real ? "REAL" : "SYNTHETIC"}</span>
                <span className="ref-src-name">{m.label}</span>
                <span className="ref-src-count">{sourceCounts[s]}</span>
                {m.sub && <span className="ref-src-sub">{m.sub}</span>}
              </div>
            );
          })}
        </div>
      </div>

      <div className="stats">
        <div className="stat"><div className="k">Active version</div><div className="v">v{doc.version}</div><div className="d">what enrichment screens against</div></div>
        <div className="stat"><div className="k">Entries</div><div className="v">{entries.length}</div><div className="d">{doc.entries.length} published{dirty ? " · unpublished edits" : ""}</div></div>
        <div className="stat"><div className="k">Last published</div><div className="v" style={{ fontSize: 15 }}>{(doc.updated_at || "").slice(0, 10) || "-"}</div><div className="d mono" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{doc.updated_by}</div></div>
      </div>

      {msg && <div className="result-ok" style={{ marginTop: 0 }}>{msg}</div>}
      {err && <div className="verdict bad">{err}</div>}

      <div className="panel">
        <h3>Entries (working copy)</h3>
        {selected.size > 0 && (
          <div className="bulkbar" role="region" aria-label="Bulk actions">
            <span><b>{selected.size}</b> selected</span>
            <button className="btn btn-red btn-sm" onClick={deleteSelected}>Delete {selected.size}</button>
            <button className="rowlink" onClick={() => setSelected(new Set())}>Clear</button>
            <span className="sub" style={{ margin: 0 }}>Publish to persist a new version.</span>
          </div>
        )}
        <div className="reftable-wrap">
          <table className="reftable reftable-edit">
            <thead><tr>
              <th className="c-sel">
                <input type="checkbox" checked={allSelected} onChange={toggleAll}
                  aria-label="Select all entries" disabled={entries.length === 0} />
              </th>
              <th>Name</th><th>TIN</th><th>Source</th><th>Severity</th><th></th>
            </tr></thead>
            <tbody>
              {entries.map((e, i) => (
                <tr key={i} className={selected.has(i) ? "row-sel" : ""}>
                  <td className="c-sel">
                    <input type="checkbox" checked={selected.has(i)} onChange={() => toggleSel(i)}
                      aria-label={`select entry ${i}`} />
                  </td>
                  <td>
                    {isIndividual(e.name, e.classification)
                      ? <span className="masked" title="Individual name masked on this surface (PII)">{mask(e.name, e.classification)}</span>
                      : <input aria-label={`entry ${i} name`} title={e.name} value={e.name} onChange={set(i, "name")} />}
                  </td>
                  <td><input aria-label={`entry ${i} tin`} className="mono" value={e.tin || ""} onChange={set(i, "tin")} /></td>
                  <td><input aria-label={`entry ${i} source`} title={e.source} value={e.source} onChange={set(i, "source")} /></td>
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
        </div>
        <div style={{ marginTop: 12, display: "flex", gap: 10 }}>
          <button className="btn btn-ghost btn-sm" onClick={addEntry}>+ Add entry</button>
          <button className="btn btn-primary btn-sm" disabled={busy || !dirty || entries.length === 0} onClick={publish}>
            {busy ? "Publishing…" : `Publish new version (v${doc.version + 1})`}
          </button>
        </div>
        <div className="note" style={{ maxWidth: "none", marginTop: 12 }}>
          Publishing never edits history: v{doc.version} stays retrievable forever, and audit
          records that cite it keep meaning exactly what they meant.
        </div>
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
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
              <table className="reftable reftable-ro">
                <thead><tr><th>Name</th><th>TIN</th><th>Source</th><th>Sev</th></tr></thead>
                <tbody>
                  {viewing.entries.map((e, i) => (
                    <tr key={i}><td>{mask(e.name, e.classification)}</td><td className="mono">{e.tin || "-"}</td><td>{e.source}</td><td>{e.severity}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
  );
}
