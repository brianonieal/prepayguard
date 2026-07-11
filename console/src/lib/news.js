// Treasury News data access. Fetches the static, SAME-ORIGIN news.json that
// scripts/fetch_news.py generates from public government + free-press feeds.
//
// SEPARATION (hard guard): this module is completely isolated from the screening
// pipeline. It does NOT import api.js (the console_api client), uses no auth/SigV4,
// touches no screening data, and calls no intake/enrichment/scoring/disposition path.
// Its only input is /news.json on the console's own origin; its only output is that
// list to the read-only news screen. Cached in localStorage so page loads don't
// refetch on every visit (the feeds themselves are only hit when fetch_news.py runs).
const CACHE_KEY = "pg.news.v1";
const TTL_MS = 20 * 60 * 1000; // 20 minutes

export async function getNews() {
  try {
    const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
    if (cached && Array.isArray(cached.items) && Date.now() - cached.at < TTL_MS) return cached.items;
  } catch { /* ignore a bad cache entry */ }

  const res = await fetch("/news.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`news feed unavailable (${res.status})`);
  const doc = await res.json();
  const items = Array.isArray(doc.items) ? doc.items : [];
  try { localStorage.setItem(CACHE_KEY, JSON.stringify({ at: Date.now(), items })); } catch { /* ignore quota */ }
  return items;
}
