import { useEffect, useState } from "react";
import { getFeedConfig, putFeedConfig, runFeed } from "../lib/api.js";
import { fetchAgencies, fetchSubAgencies, STATES, DOWNLOAD_FORMATS, requestAwardDownload, pollAwardDownload } from "../lib/usaspending.js";

// USAspending award_type_codes grouped into the builder's friendly categories.
// A single query is EITHER prime OR sub-awards (the API's subawards flag is global),
// so the mode toggle picks which set of checkboxes shows.
const PRIME = [
  { key: "contracts", label: "Contracts", codes: ["A", "B", "C", "D"] },
  { key: "idvs", label: "Contract IDVs", codes: ["IDV_A", "IDV_B", "IDV_C", "IDV_D", "IDV_E"] },
  { key: "grants", label: "Grants", codes: ["02", "03", "04", "05"] },
  { key: "direct", label: "Direct Payments", codes: ["06", "10"] },
  { key: "loans", label: "Loans", codes: ["07", "08"] },
  { key: "insurance", label: "Insurance", codes: ["09"] },
  { key: "other", label: "Other Financial Assistance", codes: ["11"] },
];
const SUB = [
  { key: "subcontracts", label: "Sub-Contracts", codes: ["A", "B", "C", "D"] },
  { key: "subgrants", label: "Sub-Grants", codes: ["02", "03", "04", "05"] },
];

const cats = (mode) => (mode === "sub" ? SUB : PRIME);
const selFromCodes = (codes, mode) => {
  const set = new Set(codes || []);
  const s = {};
  for (const c of cats(mode)) s[c.key] = c.codes.every((x) => set.has(x));
  return s;
};
const codesFromSel = (sel, mode) => cats(mode).filter((c) => sel[c.key]).flatMap((c) => c.codes);
const isoDaysAgo = (n) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10);

export default function Feed() {
  const [mode, setMode] = useState("prime");            // prime | sub
  const [sel, setSel] = useState({ contracts: true });
  const [agencyType, setAgencyType] = useState("awarding");
  const [agencies, setAgencies] = useState([]);
  const [agencyCode, setAgencyCode] = useState("");     // toptier_code
  const [subAgencies, setSubAgencies] = useState([]);
  const [subAgency, setSubAgency] = useState("");
  const [locType, setLocType] = useState("recipient");  // recipient | pop
  const [country, setCountry] = useState("USA");
  const [state, setState] = useState("");
  const [dateType, setDateType] = useState("action_date");
  const [startDate, setStartDate] = useState(isoDaysAgo(365));
  const [endDate, setEndDate] = useState(isoDaysAgo(0));
  const [limit, setLimit] = useState(10);
  const [fileFormat, setFileFormat] = useState("csv");
  const [dl, setDl] = useState(null);                   // {phase, rows?, url?, size?}
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [lastRun, setLastRun] = useState(null);

  useEffect(() => { fetchAgencies().then(setAgencies).catch(() => {}); }, []);

  useEffect(() => {
    getFeedConfig().then(({ config: c }) => {
      const m = c.subawards ? "sub" : "prime";
      setMode(m);
      setSel(selFromCodes(c.award_type_codes, m));
      setDateType(c.date_type || "action_date");
      if (c.start_date) setStartDate(c.start_date);
      if (c.end_date) setEndDate(c.end_date);
      setLimit(c.limit ?? 10);
      const ag = (c.agencies || [])[0];
      if (ag) setAgencyType(ag.type);
      const sub = (c.agencies || []).find((a) => a.tier === "subtier");
      if (sub) setSubAgency(sub.name);
      const loc = (c.recipient_locations || c.place_of_performance_locations || [])[0];
      if (c.place_of_performance_locations) setLocType("pop");
      if (loc) { setCountry(loc.country || "USA"); if (loc.state) setState(loc.state); }
      setLoaded(true);
    }).catch((e) => setErr(String(e.message || e)));
  }, []);

  // Sub-agency list follows the selected toptier agency.
  useEffect(() => {
    if (!agencyCode) { setSubAgencies([]); return; }
    fetchSubAgencies(agencyCode).then(setSubAgencies).catch(() => setSubAgencies([]));
  }, [agencyCode]);

  const setModeReset = (m) => { setMode(m); setSel(m === "sub" ? { subcontracts: true } : { contracts: true }); };
  const toggle = (k) => setSel((p) => ({ ...p, [k]: !p[k] }));
  const codes = codesFromSel(sel, mode);
  const agencyName = agencies.find((a) => a.code === agencyCode)?.name || "";

  const cfg = () => {
    const c = {
      award_type_codes: codes, subawards: mode === "sub", date_type: dateType,
      start_date: startDate, end_date: endDate, limit: Number(limit),
    };
    if (agencyName) {
      c.agencies = [{ type: agencyType, tier: "toptier", name: agencyName }];
      if (subAgency) c.agencies.push({ type: agencyType, tier: "subtier", name: subAgency });
    }
    if (country && (state || locType)) {
      const loc = [{ country, ...(state ? { state } : {}) }];
      c[locType === "pop" ? "place_of_performance_locations" : "recipient_locations"] = loc;
    }
    return c;
  };
  const noTypes = codes.length === 0;

  const doSave = async () => {
    setBusy("save"); setErr(""); setMsg("");
    try { await putFeedConfig(cfg()); setMsg("Saved. The scheduled feed will use these filters next run."); }
    catch (ex) { setErr(String(ex?.message || "save failed")); } finally { setBusy(""); }
  };
  const doRun = async () => {
    setBusy("run"); setErr(""); setMsg("");
    try {
      const r = await runFeed(cfg());
      setLastRun(r.result || {});
      setMsg(`Pulled now: ${r.result?.written ?? 0} payment(s) screened. They appear in the console shortly.`);
    } catch (ex) { setErr(String(ex?.message || "run failed")); } finally { setBusy(""); }
  };

  // USAspending Custom Award Data bulk download uses prime_award_types / sub_award_types
  // (not the feeder's award_type_codes + subawards flag) and no size cap; it exports the
  // full matching file. Built from the same builder state as the feed.
  const downloadFilters = () => {
    const f = { date_type: dateType, date_range: { start_date: startDate, end_date: endDate } };
    if (mode === "sub") {
      // The bulk download takes sub_award_types as category names, not the prime letter
      // codes (verified 2026-07-08: valid values are 'procurement' and 'grant').
      const SUB_DL = { subcontracts: "procurement", subgrants: "grant" };
      f.sub_award_types = SUB.filter((c) => sel[c.key]).map((c) => SUB_DL[c.key]);
    } else {
      f.prime_award_types = codes;
    }
    if (agencyName) {
      f.agencies = [{ type: agencyType, tier: "toptier", name: agencyName }];
      if (subAgency) f.agencies.push({ type: agencyType, tier: "subtier", name: subAgency });
    }
    if (country) {
      const loc = [{ country, ...(state ? { state } : {}) }];
      f[locType === "pop" ? "place_of_performance_locations" : "recipient_locations"] = loc;
    }
    return f;
  };

  const doDownload = async () => {
    setBusy("download"); setErr(""); setMsg(""); setDl({ phase: "requesting" });
    try {
      const req = await requestAwardDownload(downloadFilters(), fileFormat);
      setDl({ phase: "preparing" });
      const done = await pollAwardDownload(req.file_name, {
        onTick: (d) => setDl({ phase: d.status === "finished" ? "preparing" : "preparing", rows: d.total_rows }),
      });
      setDl({ phase: "ready", url: done.file_url, rows: done.total_rows, size: done.total_size });
    } catch (ex) { setErr(String(ex?.message || "download failed")); setDl(null); }
    finally { setBusy(""); }
  };

  if (err && !loaded) return <div className="body"><div className="verdict bad">Failed to load feed config: {err}</div></div>;
  if (!loaded) return <div className="body"><div className="sub">Loading feed config…</div></div>;

  return (
    <div className="body feed">
      <h2>Feed</h2>
      <div className="sub">
        Configure the real federal data the feeder pulls from USAspending: award types,
        agency, location, and date range. Save sets what the scheduled feed uses; Run now
        pulls immediately. Each pull screens real payees and writes permanent audit records.
      </div>

      {msg && <div className="result-ok" style={{ marginTop: 0, marginBottom: 16 }}>{msg}</div>}
      {err && <div className="verdict bad" style={{ marginBottom: 16 }}>{err}</div>}

      <div className="detail-grid">
        <div className="panel">
          <h3>Award types</h3>
          <div className="toggle">
            <label><input type="radio" name="mode" aria-label="Prime Awards" checked={mode === "prime"} onChange={() => setModeReset("prime")} /> Prime awards</label>
            <label><input type="radio" name="mode" aria-label="Sub-Awards" checked={mode === "sub"} onChange={() => setModeReset("sub")} /> Sub-awards</label>
          </div>
          <div className="checklist">
            {cats(mode).map((c) => (
              <label key={c.key}>
                <input type="checkbox" aria-label={c.label} checked={!!sel[c.key]} onChange={() => toggle(c.key)} /> {c.label}
              </label>
            ))}
          </div>
          {noTypes && <div className="warn">Pick at least one award type.</div>}
        </div>

        <div className="panel">
          <h3>Agency</h3>
          <div className="toggle">
            <label><input type="radio" name="agtype" aria-label="Awarding Agency" checked={agencyType === "awarding"} onChange={() => setAgencyType("awarding")} /> Awarding</label>
            <label><input type="radio" name="agtype" aria-label="Funding Agency" checked={agencyType === "funding"} onChange={() => setAgencyType("funding")} /> Funding</label>
          </div>
          <div className="field">
            <span>Agency (optional)</span>
            <select aria-label="agency" value={agencyCode} onChange={(e) => { setAgencyCode(e.target.value); setSubAgency(""); }}>
              <option value="">Any agency</option>
              {agencies.map((a) => <option key={a.code} value={a.code}>{a.name}</option>)}
            </select>
          </div>
          <div className="field">
            <span>Sub-agency (optional)</span>
            <select aria-label="sub-agency" value={subAgency} onChange={(e) => setSubAgency(e.target.value)} disabled={!subAgencies.length}>
              <option value="">Any sub-agency</option>
              {subAgencies.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>

        <div className="panel">
          <h3>Location</h3>
          <div className="toggle">
            <label><input type="radio" name="loc" aria-label="Recipient Location" checked={locType === "recipient"} onChange={() => setLocType("recipient")} /> Recipient</label>
            <label><input type="radio" name="loc" aria-label="Place of Performance" checked={locType === "pop"} onChange={() => setLocType("pop")} /> Place of performance</label>
          </div>
          <div className="field-row">
            <div className="field">
              <span>Country</span>
              <select aria-label="country" value={country} onChange={(e) => setCountry(e.target.value)}>
                <option value="USA">United States</option>
                <option value="">Any country</option>
              </select>
            </div>
            <div className="field">
              <span>State (optional)</span>
              <select aria-label="state" value={state} onChange={(e) => setState(e.target.value)}>
                <option value="">Any state</option>
                {STATES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
        </div>

        <div className="panel">
          <h3>Dates and size</h3>
          <div className="field">
            <span>Date type</span>
            <select aria-label="date type" value={dateType} onChange={(e) => setDateType(e.target.value)}>
              <option value="action_date">Action date</option>
              <option value="last_modified_date">Last modified date</option>
            </select>
          </div>
          <div className="field-row">
            <div className="field">
              <span>From</span>
              <input type="date" aria-label="from" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </div>
            <div className="field">
              <span>To</span>
              <input type="date" aria-label="to" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </div>
          </div>
          <div className="field">
            <span>Payments per pull (max 100)</span>
            <input type="number" aria-label="limit" min="1" max="100" value={limit} onChange={(e) => setLimit(e.target.value)} />
          </div>
          <div className="actions">
            <button className="btn btn-ghost btn-sm" disabled={!!busy || noTypes} onClick={doSave}>{busy === "save" ? "Saving…" : "Save"}</button>
            <button className="btn btn-primary btn-sm" disabled={!!busy || noTypes} onClick={doRun}>{busy === "run" ? "Pulling…" : "Run now"}</button>
          </div>
          {lastRun && <div className="note" style={{ maxWidth: "none", marginTop: 12 }}>Last run: {lastRun.written ?? 0} written · source {lastRun.source || "usaspending"}.</div>}
        </div>
      </div>

      <div className="panel dl-panel">
        <h3>Download the raw award file (USAspending)</h3>
        <div className="setdesc" style={{ marginBottom: 12 }}>
          Download the full matching Custom Award Data file straight from USAspending, using the
          filters above. This is a raw data export to your browser (the same file the USAspending
          download center produces); it does not run through screening.
        </div>
        <div className="dl-row">
          <div className="field" style={{ margin: 0, flex: 1 }}>
            <span>File format</span>
            <div className="toggle" style={{ marginBottom: 0 }}>
              {DOWNLOAD_FORMATS.map((f) => (
                <label key={f.value}>
                  <input type="radio" name="fmt" aria-label={f.label} checked={fileFormat === f.value} onChange={() => setFileFormat(f.value)} /> {f.label}
                </label>
              ))}
            </div>
          </div>
          <button className="btn btn-primary btn-sm" style={{ alignSelf: "flex-end" }} disabled={!!busy || noTypes} onClick={doDownload}>
            {busy === "download" ? "Preparing…" : "Download"}
          </button>
        </div>
        {dl && dl.phase !== "ready" && (
          <div className="note" style={{ maxWidth: "none", marginTop: 12 }}>
            {dl.phase === "requesting" ? "Requesting the file from USAspending…" : "USAspending is generating your file"}
            {dl.rows != null ? ` (${dl.rows.toLocaleString()} rows so far)` : ""}. A wide date range can take a minute.
          </div>
        )}
        {dl && dl.phase === "ready" && (
          <div className="result-ok" style={{ maxWidth: "none", marginTop: 12 }}>
            Your file is ready: {Number(dl.rows || 0).toLocaleString()} rows{dl.size ? `, about ${Math.round(dl.size).toLocaleString()} KB` : ""}.{" "}
            <a href={dl.url} className="rowlink" target="_blank" rel="noopener noreferrer">Download the ZIP →</a>
          </div>
        )}
      </div>
    </div>
  );
}
