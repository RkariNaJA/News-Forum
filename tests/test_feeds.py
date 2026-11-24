import json
from datetime import datetime, timedelta, timezone

from news.feeds import UNDATED_MAX, clean_text, load_feeds, normalize_link, parse_feed
from conftest import FIXTURES

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
WORLD = {"name": "Sample World", "url": "https://example.com/rss", "category": "world"}


def test_parse_rss_cleans_title_summary_and_link():
    arts = parse_feed((FIXTURES / "sample_rss.xml").read_bytes(), WORLD, now=NOW)
    assert [a["title"] for a in arts] == ["Leaders meet & agree on trade deal", "Story without a date"]
    first = arts[0]
    assert first["summary"] == "Talks ended late on Sunday."
    assert first["link"] == "https://example.com/news/trade-deal?id=7"   # tracking params gone
    assert first["image"] == "https://img.example.com/trade.jpg"
    assert first["published"] == "2026-11-15T10:00:00+00:00"
    assert first["source"] == "Sample World" and first["category"] == "world"


def test_detail_fields_author_tags_and_full_feed_text():
    xml = b"""<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>
      <title>T</title><link>https://a.com/x</link><author>Ann Writer</author>
      <category>Politics</category><category>politics</category><category>Asia</category>
      <description>Short blurb.</description>
      <content:encoded><![CDATA[<p>First paragraph.</p><p>Second<br>third line.</p>]]></content:encoded>
    </item></channel></rss>"""
    a = parse_feed(xml, WORLD, now=NOW)[0]
    assert a["author"] == "Ann Writer"
    assert a["tags"] == ["Politics", "Asia"]            # de-duplicated, case-insensitive
    assert a["feed_text"] == "First paragraph.\nSecond\nthird line."  # richer than the summary
    assert a["summary"] == "Short blurb."


def test_missing_date_falls_back_to_now():
    arts = parse_feed((FIXTURES / "sample_rss.xml").read_bytes(), WORLD, now=NOW)
    assert arts[1]["published"] == NOW.isoformat()


def test_undated_entries_are_spread_in_feed_order():
    items = "".join(f"<item><title>T{i}</title><link>https://a.com/{i}</link></item>" for i in range(3))
    arts = parse_feed(f"<rss><channel>{items}</channel></rss>".encode(), WORLD, now=NOW)
    assert [a["published"] for a in arts] == [
        NOW.isoformat(),
        (NOW - timedelta(minutes=20)).isoformat(),
        (NOW - timedelta(minutes=40)).isoformat(),
    ]


def test_parse_atom():
    feed = {"name": "Sample Tech", "url": "https://tech.example.com/feed", "category": "tech"}
    arts = parse_feed((FIXTURES / "sample_atom.xml").read_bytes(), feed, now=NOW)
    assert len(arts) == 1
    assert arts[0]["link"] == "https://tech.example.com/chip"
    assert arts[0]["published"] == "2026-11-16T03:00:00+00:00"


def test_future_dates_are_capped_to_now():
    xml = (b"<rss><channel><item><title>T</title><link>https://a.com/x</link>"
           b"<pubDate>Fri, 01 Jan 2100 00:00:00 GMT</pubDate></item></channel></rss>")
    assert parse_feed(xml, WORLD, now=NOW)[0]["published"] == NOW.isoformat()


def test_garbage_input_gives_no_articles():
    assert parse_feed(b"<html>not a feed</html>", WORLD, now=NOW) == []


def test_normalize_link_rejects_unsafe_schemes():
    assert normalize_link("javascript:alert(1)") is None
    assert normalize_link("data:text/html,hi") is None
    assert normalize_link("") is None
    assert normalize_link("https://Example.COM/a?utm_campaign=z") == "https://example.com/a"


def test_clean_text_truncates_on_word():
    assert clean_text("one two three four five", limit=12) == "one two…"


def test_load_feeds_skips_invalid_entries(tmp_path):
    p = tmp_path / "feeds.json"
    p.write_text(json.dumps({"feeds": [
        {"name": "Good", "url": "https://a.com/rss", "category": "world"},
        {"name": "Bad category", "url": "https://b.com/rss", "category": "sports"},
        {"name": "Bad scheme", "url": "file:///etc/passwd", "category": "world"},
        {"url": "https://c.com/rss", "category": "world"},
    ]}), encoding="utf-8")
    assert [f["name"] for f in load_feeds(p)] == ["Good"]


def test_real_feeds_json_is_valid():
    from news.config import FEEDS_PATH
    feeds = load_feeds(FEEDS_PATH)
    assert len(feeds) >= 20
    assert {f["category"] for f in feeds} == {"world", "business", "markets", "asia", "tech"}
    assert sum(f["category"] == "markets" for f in feeds) >= 3   # Crypto & Investing tab
    assert len({f["name"] for f in feeds}) == len(feeds)


def test_undated_feeds_are_capped():
    items = "".join(f"<item><title>T{i}</title><link>https://a.com/{i}</link></item>" for i in range(50))
    arts = parse_feed(f"<rss><channel>{items}</channel></rss>".encode(), WORLD, now=NOW)
    assert [a["title"] for a in arts] == [f"T{i}" for i in range(UNDATED_MAX)]   # the newest, in feed order


def test_feed_user_agent_does_not_pose_as_a_browser():
    # The Guardian answers 403 to a "Mozilla/..." UA from a non-browser client (Nov 2026).
    from news.feeds import USER_AGENT
    assert not USER_AGENT.startswith("Mozilla/")
