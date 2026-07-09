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

// Countries for the Location filter (ISO 3166-1 alpha-3 codes; USAspending's location
// filters take these, verified 2026-07-08). "" is the "All countries" default. US first,
// then alphabetical. Comprehensive coverage of real award-recipient countries.
export const COUNTRIES = [
  { code: "USA", name: "United States" },
  { code: "AFG", name: "Afghanistan" }, { code: "ALB", name: "Albania" }, { code: "DZA", name: "Algeria" },
  { code: "AGO", name: "Angola" }, { code: "ARG", name: "Argentina" }, { code: "ARM", name: "Armenia" },
  { code: "AUS", name: "Australia" }, { code: "AUT", name: "Austria" }, { code: "AZE", name: "Azerbaijan" },
  { code: "BHR", name: "Bahrain" }, { code: "BGD", name: "Bangladesh" }, { code: "BLR", name: "Belarus" },
  { code: "BEL", name: "Belgium" }, { code: "BEN", name: "Benin" }, { code: "BOL", name: "Bolivia" },
  { code: "BIH", name: "Bosnia and Herzegovina" }, { code: "BWA", name: "Botswana" }, { code: "BRA", name: "Brazil" },
  { code: "BGR", name: "Bulgaria" }, { code: "BFA", name: "Burkina Faso" }, { code: "BDI", name: "Burundi" },
  { code: "KHM", name: "Cambodia" }, { code: "CMR", name: "Cameroon" }, { code: "CAN", name: "Canada" },
  { code: "TCD", name: "Chad" }, { code: "CHL", name: "Chile" }, { code: "CHN", name: "China" },
  { code: "COL", name: "Colombia" }, { code: "COD", name: "Congo (Kinshasa)" }, { code: "COG", name: "Congo (Brazzaville)" },
  { code: "CRI", name: "Costa Rica" }, { code: "CIV", name: "Cote d'Ivoire" }, { code: "HRV", name: "Croatia" },
  { code: "CUB", name: "Cuba" }, { code: "CYP", name: "Cyprus" }, { code: "CZE", name: "Czechia" },
  { code: "DNK", name: "Denmark" }, { code: "DJI", name: "Djibouti" }, { code: "DOM", name: "Dominican Republic" },
  { code: "ECU", name: "Ecuador" }, { code: "EGY", name: "Egypt" }, { code: "SLV", name: "El Salvador" },
  { code: "EST", name: "Estonia" }, { code: "ETH", name: "Ethiopia" }, { code: "FIN", name: "Finland" },
  { code: "FRA", name: "France" }, { code: "GAB", name: "Gabon" }, { code: "GEO", name: "Georgia" },
  { code: "DEU", name: "Germany" }, { code: "GHA", name: "Ghana" }, { code: "GRC", name: "Greece" },
  { code: "GTM", name: "Guatemala" }, { code: "GIN", name: "Guinea" }, { code: "HTI", name: "Haiti" },
  { code: "HND", name: "Honduras" }, { code: "HUN", name: "Hungary" }, { code: "ISL", name: "Iceland" },
  { code: "IND", name: "India" }, { code: "IDN", name: "Indonesia" }, { code: "IRN", name: "Iran" },
  { code: "IRQ", name: "Iraq" }, { code: "IRL", name: "Ireland" }, { code: "ISR", name: "Israel" },
  { code: "ITA", name: "Italy" }, { code: "JAM", name: "Jamaica" }, { code: "JPN", name: "Japan" },
  { code: "JOR", name: "Jordan" }, { code: "KAZ", name: "Kazakhstan" }, { code: "KEN", name: "Kenya" },
  { code: "KOR", name: "Korea, South" }, { code: "KWT", name: "Kuwait" }, { code: "KGZ", name: "Kyrgyzstan" },
  { code: "LAO", name: "Laos" }, { code: "LVA", name: "Latvia" }, { code: "LBN", name: "Lebanon" },
  { code: "LBR", name: "Liberia" }, { code: "LBY", name: "Libya" }, { code: "LTU", name: "Lithuania" },
  { code: "LUX", name: "Luxembourg" }, { code: "MDG", name: "Madagascar" }, { code: "MWI", name: "Malawi" },
  { code: "MYS", name: "Malaysia" }, { code: "MLI", name: "Mali" }, { code: "MEX", name: "Mexico" },
  { code: "MDA", name: "Moldova" }, { code: "MNG", name: "Mongolia" }, { code: "MAR", name: "Morocco" },
  { code: "MOZ", name: "Mozambique" }, { code: "MMR", name: "Myanmar" }, { code: "NAM", name: "Namibia" },
  { code: "NPL", name: "Nepal" }, { code: "NLD", name: "Netherlands" }, { code: "NZL", name: "New Zealand" },
  { code: "NIC", name: "Nicaragua" }, { code: "NER", name: "Niger" }, { code: "NGA", name: "Nigeria" },
  { code: "NOR", name: "Norway" }, { code: "OMN", name: "Oman" }, { code: "PAK", name: "Pakistan" },
  { code: "PAN", name: "Panama" }, { code: "PNG", name: "Papua New Guinea" }, { code: "PRY", name: "Paraguay" },
  { code: "PER", name: "Peru" }, { code: "PHL", name: "Philippines" }, { code: "POL", name: "Poland" },
  { code: "PRT", name: "Portugal" }, { code: "QAT", name: "Qatar" }, { code: "ROU", name: "Romania" },
  { code: "RUS", name: "Russia" }, { code: "RWA", name: "Rwanda" }, { code: "SAU", name: "Saudi Arabia" },
  { code: "SEN", name: "Senegal" }, { code: "SRB", name: "Serbia" }, { code: "SLE", name: "Sierra Leone" },
  { code: "SGP", name: "Singapore" }, { code: "SVK", name: "Slovakia" }, { code: "SVN", name: "Slovenia" },
  { code: "SOM", name: "Somalia" }, { code: "ZAF", name: "South Africa" }, { code: "SSD", name: "South Sudan" },
  { code: "ESP", name: "Spain" }, { code: "LKA", name: "Sri Lanka" }, { code: "SDN", name: "Sudan" },
  { code: "SWE", name: "Sweden" }, { code: "CHE", name: "Switzerland" }, { code: "SYR", name: "Syria" },
  { code: "TWN", name: "Taiwan" }, { code: "TJK", name: "Tajikistan" }, { code: "TZA", name: "Tanzania" },
  { code: "THA", name: "Thailand" }, { code: "TGO", name: "Togo" }, { code: "TUN", name: "Tunisia" },
  { code: "TUR", name: "Turkey" }, { code: "TKM", name: "Turkmenistan" }, { code: "UGA", name: "Uganda" },
  { code: "UKR", name: "Ukraine" }, { code: "ARE", name: "United Arab Emirates" }, { code: "GBR", name: "United Kingdom" },
  { code: "URY", name: "Uruguay" }, { code: "UZB", name: "Uzbekistan" }, { code: "VEN", name: "Venezuela" },
  { code: "VNM", name: "Vietnam" }, { code: "YEM", name: "Yemen" }, { code: "ZMB", name: "Zambia" },
  { code: "ZWE", name: "Zimbabwe" },
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
