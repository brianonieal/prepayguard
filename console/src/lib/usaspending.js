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
