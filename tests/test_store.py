from datetime import datetime, timedelta, timezone

import pytest

from news.store import Store

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def art(link, category="world", hours_ago=1, title=None):
    return {"link": link, "title": title or f"Title {link}", "summary": "s", "source": "Src",
            "category": category, "image": None,
            "published": (NOW - timedelta(hours=hours_ago)).isoformat()}


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "news.db")


def test_duplicate_links_are_ignored(store):
    assert store.add_articles([art("https://a/1"), art("https://a/2")], now=NOW) == 2
    assert store.add_articles([art("https://a/1"), art("https://a/3")], now=NOW) == 1
    assert len(store.list_articles("world", now=NOW)) == 3


def test_views_today_category_saved(store):
    store.add_articles([art("https://a/1", "world", 2), art("https://a/2", "tech", 30),
                        art("https://a/3", "asia", 5)], now=NOW)
    today = store.list_articles("today", now=NOW)
    assert [a["link"] for a in today] == ["https://a/1", "https://a/3"]  # newest first, 24h only
    assert [a["link"] for a in store.list_articles("tech", now=NOW)] == ["https://a/2"]
    assert store.list_articles("saved", now=NOW) == []
    store.set_flag(today[0]["id"], "saved", True)
    assert [a["link"] for a in store.list_articles("saved", now=NOW)] == ["https://a/1"]


def test_search_escapes_like_wildcards(store):
    store.add_articles([art("https://a/1", title="100% growth"), art("https://a/2", title="Rates")], now=NOW)
    assert [a["link"] for a in store.list_articles("world", q="100%", now=NOW)] == ["https://a/1"]
    assert [a["link"] for a in store.list_articles("world", q="%", now=NOW)] == ["https://a/1"]
    assert len(store.list_articles("world", q="rates", now=NOW)) == 1   # case-insensitive


def test_flags_and_counts(store):
    store.add_articles([art("https://a/1"), art("https://a/2", "tech")], now=NOW)
    ids = [a["id"] for a in store.list_articles("today", now=NOW)]
    assert store.counts(now=NOW)["today"] == 2
    assert store.set_flag(ids[0], "is_read", True)
    assert store.counts(now=NOW)["today"] == 1
    assert store.set_flag(9999, "is_read", True) is False
    assert store.mark_all_read(ids) == 2
    assert store.counts(now=NOW)["today"] == 0
    with pytest.raises(ValueError):
        store.set_flag(ids[0], "title", True)


def test_prune_keeps_saved_articles(store):
    store.add_articles([art("https://old/1", hours_ago=24 * 40), art("https://old/2", hours_ago=24 * 40),
                        art("https://new/1")], now=NOW)
    old_saved = [a for a in store.list_articles("world", now=NOW) if a["link"] == "https://old/2"][0]
    store.set_flag(old_saved["id"], "saved", True)
    assert store.prune(30, now=NOW) == 1
    assert {a["link"] for a in store.list_articles("world", now=NOW)} == {"https://old/2", "https://new/1"}


def test_get_article_and_detail_backfill(store):
    store.add_articles([art("https://a/1")], now=NOW)              # stored before detail fields
    a = store.get_article(store.list_articles("world", now=NOW)[0]["id"])
    assert a["tags"] == [] and a["feed_text"] == ""
    store.add_articles([{**art("https://a/1"), "author": "Ann", "tags": ["X"], "feed_text": "Full."}], now=NOW)
    a = store.get_article(a["id"])
    assert (a["author"], a["tags"], a["feed_text"]) == ("Ann", ["X"], "Full.")
    assert store.get_article(9999) is None


def test_old_database_is_migrated(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as c:   # the first-release schema, without the detail columns
        c.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT NOT NULL UNIQUE,"
                  " title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', source TEXT NOT NULL,"
                  " category TEXT NOT NULL, image TEXT, published TEXT NOT NULL, fetched TEXT NOT NULL,"
                  " is_read INTEGER NOT NULL DEFAULT 0, saved INTEGER NOT NULL DEFAULT 0)")
        c.execute("INSERT INTO articles (link, title, source, category, published, fetched, saved)"
                  " VALUES ('https://old/1', 'Old', 'S', 'world', ?, ?, 1)", (NOW.isoformat(), NOW.isoformat()))
    s = Store(db)
    old = s.list_articles("saved", now=NOW)[0]
    assert old["title"] == "Old" and s.get_article(old["id"])["feed_text"] == ""


def test_reader_cache_ok_forever_failures_retry(store):
    store.add_articles([art("https://a/1"), art("https://a/2")], now=NOW)
    ids = [a["id"] for a in store.list_articles("world", now=NOW)]
    assert store.get_reader(ids[0], now=NOW) is None
    store.save_reader(ids[0], {"paragraphs": ["p"], "author": None, "date": None, "image": None}, None, now=NOW)
    assert store.get_reader(ids[0], now=NOW + timedelta(days=20))["paragraphs"] == ["p"]
    store.save_reader(ids[1], None, "blocked", now=NOW)
    assert store.get_reader(ids[1], now=NOW + timedelta(hours=1)) == {"ok": False, "error": "blocked"}
    assert store.get_reader(ids[1], now=NOW + timedelta(hours=7)) is None   # old failure: try again


def test_prune_drops_orphaned_reader_cache(store):
    store.add_articles([art("https://old/1", hours_ago=24 * 40)], now=NOW)
    aid = store.list_articles("world", now=NOW)[0]["id"]
    store.save_reader(aid, {"paragraphs": ["p"]}, None, now=NOW)
    store.prune(30, now=NOW)
    assert store.get_reader(aid, now=NOW) is None


def test_record_fetch_keeps_last_ok_on_error(store):
    feed = {"name": "F", "url": "https://f/rss", "category": "world"}
    store.record_fetch(feed, 10, None, now=NOW)
    store.record_fetch(feed, 0, "boom", now=NOW + timedelta(hours=1))
    st = store.feed_statuses()["F"]
    assert st["error"] == "boom" and st["last_ok"] == NOW.isoformat() and st["last_count"] == 0
