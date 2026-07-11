import { useEffect, useState } from "react";
import { getNews } from "../lib/news.js";

// Read-only news panel. Display-only content with ZERO connection to the screening
// pipeline: it renders the same-origin news.json via lib/news.js and shares no data
// path, tool, or state with intake / enrichment / scoring / disposition.
//
// Two sections grouped by source tier: Government (official, always free) leads, then
// Press (reputable, non-paywalled). Each section shows the newest few items.
const PER_SECTION = 5;

function NewsCard({ it }) {
  return (
    <article className="news-card">
      <div className="news-head">
        <span className={`news-src ${it.tier === "government" ? "gov" : "press"}`}>{it.source}</span>
        {it.date && <span className="news-date">{it.date}</span>}
      </div>
      <h3 className="news-title">{it.title}</h3>
      {it.summary && <p className="news-summary">{it.summary}</p>}
      <a className="news-link" href={it.link} target="_blank" rel="noopener noreferrer">
        Read at {it.source} →
      </a>
    </article>
  );
}

function NewsSection({ title, note, items }) {
  if (!items.length) return null;
  return (
    <section className="news-section">
      <div className="news-section-head">
        <h3 className="news-section-title">{title}</h3>
        <span className="news-section-note">{note}</span>
      </div>
      <div className="news-list">
        {items.map((it, i) => <NewsCard it={it} key={i} />)}
      </div>
    </section>
  );
}

export default function TreasuryNews() {
  const [data, setData] = useState(null); // null = loading, { items, generatedAt }
  const [err, setErr] = useState("");

  useEffect(() => {
    getNews().then(setData).catch((e) => { setErr(String(e?.message || e)); setData({ items: [], generatedAt: null }); });
  }, []);

  const items = data?.items || [];
  const gov = items.filter((i) => i.tier === "government").slice(0, PER_SECTION);
  const press = items.filter((i) => i.tier === "press").slice(0, PER_SECTION);

  return (
    <div className="body">
      <h2>Treasury News</h2>
      <div className="sub">
        Public federal financial-oversight news from free government and press sources. Read-only
        and completely separate from the screening pipeline: this panel shares no data with the
        pay / no-pay decision. Every link opens the original article at its source.
      </div>

      {data === null && !err && <div className="sub">Loading news…</div>}
      {err && <div className="verdict bad">Couldn't load the news feed right now: {err}</div>}
      {data && items.length === 0 && !err && <div className="sub">No news items available right now.</div>}
      {data?.generatedAt && (
        <div className="news-updated">Last updated {new Date(data.generatedAt).toLocaleString()}</div>
      )}

      <NewsSection title="Government sources" note="Official · always free · public record" items={gov} />
      <NewsSection title="Press" note="Reputable · non-paywalled outlets" items={press} />
    </div>
  );
}
