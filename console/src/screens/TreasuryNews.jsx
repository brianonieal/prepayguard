import { useEffect, useState } from "react";
import { getNews } from "../lib/news.js";

// Read-only news panel. Display-only content with ZERO connection to the screening
// pipeline: it renders the same-origin news.json via lib/news.js and shares no data
// path, tool, or state with intake / enrichment / scoring / disposition.
export default function TreasuryNews() {
  const [items, setItems] = useState(null); // null = loading, [] = none, [...] = items
  const [err, setErr] = useState("");

  useEffect(() => {
    getNews().then(setItems).catch((e) => { setErr(String(e?.message || e)); setItems([]); });
  }, []);

  return (
    <div className="body">
      <h2>Treasury News</h2>
      <div className="sub">
        Public federal financial-oversight news from free government and press sources. Read-only
        and completely separate from the screening pipeline: this panel shares no data with the
        pay / no-pay decision. Every link opens the original article at its source.
      </div>

      {items === null && !err && <div className="sub">Loading news…</div>}
      {err && <div className="verdict bad">Couldn't load the news feed right now: {err}</div>}
      {items && items.length === 0 && !err && <div className="sub">No news items available right now.</div>}

      <div className="news-list">
        {(items || []).map((it, i) => (
          <article className="news-card" key={i}>
            <div className="news-head">
              <span className="news-src">{it.source}</span>
              {it.date && <span className="news-date">{it.date}</span>}
            </div>
            <h3 className="news-title">{it.title}</h3>
            {it.summary && <p className="news-summary">{it.summary}</p>}
            <a className="news-link" href={it.link} target="_blank" rel="noopener noreferrer">
              Read at {it.source} →
            </a>
          </article>
        ))}
      </div>
    </div>
  );
}
