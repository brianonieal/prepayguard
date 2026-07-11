"""Deterministic tests for the Treasury News fetcher (scripts/fetch_news.py).

No network: pins HTML cleaning, the 3-4 sentence summary trim (which must NEVER
fabricate, only trim what the feed gave), RSS 2.0 + Atom parsing, the Federal Register
JSON mapping, and the skip-incomplete-items rule.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load():
    path = ROOT / "scripts" / "fetch_news.py"
    spec = importlib.util.spec_from_file_location("fetch_news", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_clean_text_strips_html_and_entities():
    fn = _load()
    assert fn.clean_text("<p>Hello &amp; <b>world</b></p>") == "Hello & world"
    assert fn.clean_text("") == ""


def test_summarize_trims_to_four_sentences_without_fabricating():
    fn = _load()
    desc = "First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence."
    out = fn.summarize(desc, "Title")
    assert out == "First sentence. Second sentence. Third sentence. Fourth sentence."
    assert "Fifth" not in out  # trimmed, and nothing invented


def test_summarize_falls_back_to_title_when_no_description():
    fn = _load()
    assert fn.summarize("", "Only a title here") == "Only a title here"
    assert fn.summarize(None, "<b>Title</b>") == "Title"  # cleaned, not fabricated


def test_parse_rss_reads_rss2_item():
    fn = _load()
    rss = (b'<?xml version="1.0"?><rss version="2.0"><channel>'
           b'<item><title>GAO Report</title><link>https://www.gao.gov/products/gao-26-1</link>'
           b'<description>&lt;p&gt;What GAO Found. Improper payments rose.&lt;/p&gt;</description>'
           b'<pubDate>Thu, 10 Jul 2026 12:00:00 GMT</pubDate></item></channel></rss>')
    items = fn.parse_rss(rss, "GAO", 6)
    assert len(items) == 1
    assert items[0]["source"] == "GAO" and items[0]["title"] == "GAO Report"
    assert items[0]["link"] == "https://www.gao.gov/products/gao-26-1"
    assert "Improper payments" in items[0]["summary"]
    assert items[0]["date"] == "2026-07-10"


def test_parse_rss_reads_atom_with_link_href():
    fn = _load()
    atom = (b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
            b'<entry><title>Atom Item</title><link href="https://example.gov/a"/>'
            b'<summary>Some summary.</summary><updated>2026-07-09T00:00:00Z</updated></entry></feed>')
    items = fn.parse_rss(atom, "Src", 6)
    assert items[0]["link"] == "https://example.gov/a"
    assert items[0]["date"] == "2026-07-09"


def test_parse_json_federal_register_maps_results():
    fn = _load()
    data = (b'{"results":[{"title":"Treasury Rule","abstract":"An abstract.",'
            b'"html_url":"https://www.federalregister.gov/documents/x","publication_date":"2026-07-11"}]}')
    items = fn.parse_json_federal_register(data, "Federal Register", 6)
    assert items[0]["title"] == "Treasury Rule"
    assert items[0]["link"].startswith("https://www.federalregister.gov")
    assert items[0]["summary"] == "An abstract." and items[0]["date"] == "2026-07-11"


def test_every_feed_has_a_valid_tier_and_both_sections_exist():
    fn = _load()
    assert all(f.get("tier") in ("government", "press") for f in fn.FEEDS)
    assert {f["tier"] for f in fn.FEEDS} == {"government", "press"}  # both sections represented
    # No paywalled / social sources slipped in.
    urls = " ".join(f["url"] for f in fn.FEEDS).lower()
    assert not any(x in urls for x in ("bloomberg", "wsj.com", "twitter", "x.com", "facebook"))


def test_drop_future_removes_articles_dated_after_today():
    fn = _load()
    items = [{"date": "2026-07-13"}, {"date": "2026-07-11"}, {"date": None}, {"date": "2026-07-10"}]
    out = fn.drop_future(items, "2026-07-11")
    assert [i["date"] for i in out] == ["2026-07-11", None, "2026-07-10"]  # future dropped, undated kept


def test_federal_register_feed_is_bounded_to_today():
    fn = _load()
    fr = next(f for f in fn.FEEDS if f["source"] == "Federal Register")
    assert "publication_date][lte]={today}" in fr["url"]  # no future-scheduled docs at the source


def test_parse_skips_items_missing_title_or_link():
    fn = _load()
    rss = (b'<?xml version="1.0"?><rss version="2.0"><channel>'
           b'<item><title>No link</title></item>'
           b'<item><link>https://x.gov/y</link></item></channel></rss>')
    assert fn.parse_rss(rss, "S", 6) == []
