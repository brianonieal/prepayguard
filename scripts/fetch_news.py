#!/usr/bin/env python3
"""Fetch "Treasury News" from a WHITELIST of free, public government + reputable-free-press
feeds and write a static news.json for the console to serve same-origin.

This is display-only content and is COMPLETELY SEPARATE from the screening pipeline:
it imports nothing from component_a/b/c/d (or e/f/g), touches no DynamoDB table, no SQS
queue, no reference/audit store, and no screening IAM. Its only inputs are the public
feeds below; its only output is console/public/news.json. The feeds are hit ONLY when
this script runs (deploy / schedule), never on a console page load.

Source whitelist (chosen so links are NOT paywalled; no Bloomberg/WSJ, no social media):
  - Federal Register API (Treasury dept, financial rules) - JSON, CORS-open, always free
  - GAO reports - improper-payments / financial oversight, prioritized
  - Government Executive, Federal News Network - reliably-free federal press

A dead/unreachable/garbled feed is skipped with a logged warning; the others still publish.
Summaries use the feed's OWN description (HTML stripped, trimmed to 3-4 sentences). If a feed
gives only a title, the title is shown as-is. Nothing is fabricated.

Usage:
  python scripts/fetch_news.py [--out console/public/news.json] [--per-source 6] [--max 30]
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

UA = "PrePayGuard-news/1.0 (capstone; display-only)"

# WHITELIST. Every entry is a free, public, non-paywalled source. type: "json" (Federal
# Register) or "rss" (RSS 2.0 / Atom). To add a source, add a free feed here - never a
# paywalled outlet (Bloomberg/WSJ) and never social media.
FEEDS = [
    {"source": "Federal Register", "type": "json",
     "url": "https://www.federalregister.gov/api/v1/documents.json?per_page=8&order=newest"
            "&fields[]=title&fields[]=abstract&fields[]=html_url&fields[]=publication_date"
            "&conditions[agencies][]=treasury-department",
     "note": "Treasury financial rules"},
    {"source": "GAO", "type": "rss", "url": "https://www.gao.gov/rss/reports.xml",
     "note": "improper payments / financial oversight"},
    # Omitted (checked, not fabricated): Treasury.gov exposes no clean press RSS (the
    # obvious URLs 404), so Treasury content is surfaced via the Federal Register feed
    # above; Oversight.gov's only public feed (rss.xml) is a site-nav feed, not OIG
    # reports (its /api/v1/reports 404s), and GAO already covers federal oversight.
    {"source": "Government Executive", "type": "rss", "url": "https://www.govexec.com/rss/all/",
     "note": "free federal press"},
    {"source": "Federal News Network", "type": "rss", "url": "https://federalnewsnetwork.com/feed/",
     "note": "free federal press"},
]

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
# Split on sentence-ending punctuation followed by whitespace (keeps decimals/abbrevs mostly intact).
_SENT = re.compile(r"(?<=[.!?])\s+")


def clean_text(raw: str) -> str:
    """Strip HTML/entities and collapse whitespace - never invents text."""
    if not raw:
        return ""
    txt = html.unescape(_TAG.sub(" ", raw))
    return _WS.sub(" ", txt).strip()


def summarize(desc: str, title: str, max_sentences: int = 4, max_chars: int = 600) -> str:
    """Use the feed's OWN description, trimmed to 3-4 sentences. No description -> the title
    as-is. Never fabricates: only trims what the feed provided."""
    body = clean_text(desc)
    if not body:
        return clean_text(title)  # feed gave only a title; show it as-is
    sentences = _SENT.split(body)
    out = " ".join(sentences[:max_sentences]).strip()
    if len(out) > max_chars:  # hard cap for a runaway single "sentence"
        out = out[:max_chars].rsplit(" ", 1)[0].rstrip(".,;:") + "…"
    return out


def _get(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https whitelist)
        return r.read()


def _norm_date(raw: str) -> str | None:
    """Best-effort ISO date (YYYY-MM-DD) from RSS/Atom/JSON date strings; None if unknown."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    return m.group(1) if m else None


def parse_json_federal_register(data: bytes, source: str, per_source: int) -> list[dict]:
    doc = json.loads(data)
    items = []
    for r in (doc.get("results") or [])[:per_source]:
        link = r.get("html_url")
        title = clean_text(r.get("title"))
        if not (link and title):
            continue
        items.append({"source": source, "title": title,
                      "summary": summarize(r.get("abstract"), title),
                      "link": link, "date": _norm_date(r.get("publication_date"))})
    return items


def _findtext(el, *paths) -> str:
    for p in paths:
        found = el.find(p)
        if found is not None and (found.text or "").strip():
            return found.text
    return ""


def parse_rss(data: bytes, source: str, per_source: int) -> list[dict]:
    """Parse RSS 2.0 or Atom, tolerating namespaces. Returns normalized items."""
    root = ET.fromstring(data)
    # Strip namespaces so find() works for both RSS and Atom.
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    entries = root.findall(".//item") or root.findall(".//entry")
    items = []
    for e in entries[:per_source]:
        title = clean_text(_findtext(e, "title"))
        # RSS <link>text</link>; Atom <link href=...>
        link = (_findtext(e, "link") or "").strip()
        if not link:
            a = e.find("link")
            if a is not None:
                link = (a.get("href") or "").strip()
        if not (title and link):
            continue
        desc = _findtext(e, "description", "summary", "content", "encoded")
        date = _norm_date(_findtext(e, "pubDate", "published", "updated", "date"))
        items.append({"source": source, "title": title,
                      "summary": summarize(desc, title), "link": link, "date": date})
    return items


def fetch_all(per_source: int) -> tuple[list[dict], list[str]]:
    """Fetch every whitelisted feed; a failure on one is logged and skipped (the rest publish)."""
    items, live, dead = [], [], []
    for f in FEEDS:
        try:
            raw = _get(f["url"])
            got = (parse_json_federal_register if f["type"] == "json" else parse_rss)(raw, f["source"], per_source)
            if got:
                items.extend(got)
                live.append(f"{f['source']} ({len(got)})")
            else:
                dead.append(f"{f['source']} (0 items parsed)")
        except Exception as exc:  # noqa: BLE001 - a dead feed must not kill the others
            dead.append(f"{f['source']} ({type(exc).__name__})")
            print(f"  WARN: {f['source']} skipped: {exc}", file=sys.stderr)
    return items, live if not dead else live + [f"SKIPPED: {d}" for d in dead]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="console/public/news.json")
    ap.add_argument("--per-source", type=int, default=6)
    ap.add_argument("--max", type=int, default=30)
    ap.add_argument("--generated-at", default=None, help="ISO timestamp (else omitted; no wall-clock in tests)")
    args = ap.parse_args()

    items, status = fetch_all(args.per_source)
    # Sort newest-first (undated sink to the bottom), cap the total.
    items.sort(key=lambda x: x.get("date") or "", reverse=True)
    items = items[:args.max]

    doc = {"items": items}
    if args.generated_at:
        doc["generated_at"] = args.generated_at
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)

    by_source = {}
    for it in items:
        by_source[it["source"]] = by_source.get(it["source"], 0) + 1
    print(f"Wrote {args.out}: {len(items)} items")
    print(f"  by source: {by_source}")
    print(f"  feeds: {', '.join(status)}")


if __name__ == "__main__":
    main()
