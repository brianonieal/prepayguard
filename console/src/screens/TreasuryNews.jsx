import { useEffect, useState } from "react";
import { getNews } from "../lib/news.js";

// Read-only news panel. Display-only, with ZERO connection to the screening pipeline:
// it renders the same-origin news.json via lib/news.js and shares no data path, tool, or
// state with intake / enrichment / scoring / disposition.
//
// View / sort / search are PURE CLIENT-SIDE filtering + rendering of the already-loaded
// items: no new fetches, no backend. State is component-local (not persisted).
const PER_SECTION = 5;
const VIEWS = ["list", "grid", "magazine"];
const label = (v) => v[0].toUpperCase() + v.slice(1);

function sortItems(items, sort) {
  const arr = [...items];
  const byDate = (dir) => (a, b) => {
    if (!a.date && !b.date) return 0;
    if (!a.date) return 1;    // undated always last
    if (!b.date) return -1;
    return dir * a.date.localeCompare(b.date);
  };
  if (sort === "oldest") arr.sort(byDate(1));
  else if (sort === "source") arr.sort((a, b) => a.source.localeCompare(b.source) || byDate(-1)(a, b));
  else arr.sort(byDate(-1)); // newest (default)
  return arr;
}

const matches = (it, q) =>
  (`${it.title} ${it.summary || ""} ${it.source}`).toLowerCase().includes(q);

function SourceBadge({ it }) {
  return <span className={`news-src ${it.tier === "government" ? "gov" : "press"}`}>{it.source}</span>;
}

function NewsCard({ it, featured }) {
  return (
    <article className={`news-card${featured ? " news-featured" : ""}`}>
      <div className="news-head">
        <SourceBadge it={it} />
        {it.date && <span className="news-date">{it.date}</span>}
      </div>
      <h3 className={`news-title${featured ? " news-title-lg" : ""}`}>{it.title}</h3>
      {it.summary && <p className="news-summary">{it.summary}</p>}
      <a className="news-link" href={it.link} target="_blank" rel="noopener noreferrer">
        Read at {it.source} →
      </a>
    </article>
  );
}

function CompactRow({ it }) {
  return (
    <a className="news-compact" href={it.link} target="_blank" rel="noopener noreferrer">
      <SourceBadge it={it} />
      <span className="news-compact-title">{it.title}</span>
      {it.date && <span className="news-date">{it.date}</span>}
    </a>
  );
}

// Render a list of items in the chosen view. Same items, three layouts.
function ItemsView({ items, view }) {
  if (!items.length) return null;
  if (view === "magazine") {
    const [lead, ...rest] = items;
    return (
      <div className="news-mag">
        <NewsCard it={lead} featured />
        {rest.length > 0 && (
          <div className="news-compact-list">
            {rest.map((it, i) => <CompactRow it={it} key={i} />)}
          </div>
        )}
      </div>
    );
  }
  return (
    <div className={view === "grid" ? "news-grid" : "news-list"}>
      {items.map((it, i) => <NewsCard it={it} key={i} />)}
    </div>
  );
}

function Section({ title, note, items, view }) {
  if (!items.length) return null;
  return (
    <section className="news-section">
      <div className="news-section-head">
        <h3 className="news-section-title">{title}</h3>
        <span className="news-section-note">{note}</span>
      </div>
      <ItemsView items={items} view={view} />
    </section>
  );
}

export default function TreasuryNews() {
  const [data, setData] = useState(null); // null = loading, { items, generatedAt }
  const [err, setErr] = useState("");
  const [view, setView] = useState("list");     // component-local only (not persisted)
  const [sort, setSort] = useState("newest");
  const [query, setQuery] = useState("");

  useEffect(() => {
    getNews().then(setData).catch((e) => { setErr(String(e?.message || e)); setData({ items: [], generatedAt: null }); });
  }, []);

  const items = data?.items || [];
  const q = query.trim().toLowerCase();
  const sorted = sortItems(items, sort);

  let body = null;
  if (data && !err) {
    if (q) {
      // Query present -> FLATTEN both tiers to one "Results" list (each card keeps its badge).
      const results = sorted.filter((it) => matches(it, q));
      body = (
        <section className="news-section">
          <div className="news-section-head">
            <h3 className="news-section-title">Results</h3>
            <span className="news-section-note">
              {results.length} result{results.length === 1 ? "" : "s"} for "{query.trim()}"
            </span>
          </div>
          {results.length === 0
            ? <div className="sub">No news items match "{query.trim()}".</div>
            : <ItemsView items={results} view={view} />}
        </section>
      );
    } else {
      // No query -> the normal two tiers, Government first, each capped to the newest few.
      const gov = sorted.filter((i) => i.tier === "government").slice(0, PER_SECTION);
      const press = sorted.filter((i) => i.tier === "press").slice(0, PER_SECTION);
      body = (
        <>
          <Section title="Government sources" note="Official · always free · public record" items={gov} view={view} />
          <Section title="Press" note="Reputable · non-paywalled outlets" items={press} view={view} />
        </>
      );
    }
  }

  return (
    <div className="body">
      <h2>Treasury News</h2>
      <div className="sub">
        Public federal financial-oversight news from free government and press sources. Read-only
        and completely separate from the screening pipeline: this panel shares no data with the
        pay / no-pay decision. Every link opens the original article at its source.
      </div>

      <div className="news-controls">
        <input className="news-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Search headlines and summaries" aria-label="Search headlines and summaries" />
        <select className="news-sort" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort news">
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="source">Source (A-Z)</option>
        </select>
        <div className="news-viewtoggle" role="group" aria-label="View">
          {VIEWS.map((v) => (
            <button key={v} className={view === v ? "on" : ""} aria-pressed={view === v} onClick={() => setView(v)}>
              {label(v)}
            </button>
          ))}
        </div>
      </div>

      {data === null && !err && <div className="sub">Loading news…</div>}
      {err && <div className="verdict bad">Couldn't load the news feed right now: {err}</div>}
      {data && items.length === 0 && !err && <div className="sub">No news items available right now.</div>}
      {data?.generatedAt && (
        <div className="news-updated">Last updated {new Date(data.generatedAt).toLocaleString()}</div>
      )}

      {body}
    </div>
  );
}
