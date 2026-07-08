// Keyless USAspending reference fetches for the Feed builder. USAspending sends
// Access-Control-Allow-Origin: * (verified 2026-07-07), so the browser calls it
// directly; the actual pull still goes through the console API -> feeder.
const BASE = "https://api.usaspending.gov/api/v2";

export async function fetchAgencies() {
  const r = await fetch(`${BASE}/references/toptier_agencies/`);
  if (!r.ok) return [];
  const d = await r.json();
  return (d.results || [])
    .map((a) => ({ name: a.agency_name, code: a.toptier_code }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

export async function fetchSubAgencies(toptierCode) {
  if (!toptierCode) return [];
  const r = await fetch(`${BASE}/agency/${toptierCode}/sub_agency/`);
  if (!r.ok) return [];
  const d = await r.json();
  // De-dupe names (a toptier can list a sub-agency more than once).
  return [...new Set((d.results || []).map((s) => s.name).filter(Boolean))];
}

export const STATES = [
  "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
  "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
  "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
  "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR", "VI", "GU", "AS", "MP",
];

// The three file formats the USAspending Custom Award Data download accepts
// (verified 2026-07-08). "pstxt" is the pipe-delimited TXT option.
export const DOWNLOAD_FORMATS = [
  { value: "csv", label: "CSV" },
  { value: "tsv", label: "TSV" },
  { value: "pstxt", label: "TXT (pipe-delimited)" },
];

// Kick off a Custom Award Data bulk download. Same keyless, CORS-open host as the
// reference fetches (POST verified CORS-open 2026-07-08). Returns
// { file_name, file_url, status_url }. The file is generated asynchronously, so the
// caller polls pollAwardDownload(file_name) until it is ready.
export async function requestAwardDownload(filters, fileFormat = "csv") {
  const r = await fetch(`${BASE}/bulk_download/awards/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filters, file_format: fileFormat }),
  });
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json()).detail || ""; } catch { /* ignore */ }
    throw new Error(`USAspending download request failed (${r.status})${detail ? ": " + detail : ""}`);
  }
  return r.json();
}

// Poll the download status until the ZIP is generated. Calls onTick(status) each
// poll so the UI can show progress. Resolves with the finished status (has file_url).
export async function pollAwardDownload(fileName, { onTick, intervalMs = 2500, maxTries = 160 } = {}) {
  const url = `${BASE}/download/status?file_name=${encodeURIComponent(fileName)}`;
  for (let i = 0; i < maxTries; i++) {
    const d = await (await fetch(url)).json();
    if (onTick) onTick(d);
    if (d.status === "finished") return d;
    if (d.status === "failed") throw new Error(d.message || "USAspending could not generate the file.");
    await new Promise((res) => setTimeout(res, intervalMs));
  }
  throw new Error("Download timed out. Try a narrower date range.");
}
