import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from news.server import create_app

BASE = "http://127.0.0.1:8770"   # the server only answers requests addressed to this PC


def local_client(app):
    return TestClient(app, base_url=BASE)


@pytest.fixture
def setup(tmp_path):
    feeds = tmp_path / "feeds.json"
    feeds.write_text(json.dumps({"feeds": [
        {"name": "Good", "url": "https://good/rss", "category": "world"},
        {"name": "Broken", "url": "https://broken/rss", "category": "tech"},
    ]}), encoding="utf-8")
    calls = []

    def fake_fetch(todo):
        calls.append([f["name"] for f in todo])
        now = datetime.now(timezone.utc).isoformat()
        return {"Good": ([{"link": "https://good/1", "title": "Hello", "summary": "", "source": "Good",
                           "category": "world", "image": None, "published": now}], None),
                "Broken": ([], "ConnectError: down")}

    client = local_client(create_app(feeds, tmp_path / "news.db", fetcher=fake_fetch))
    return client, calls


def test_refresh_stores_articles_and_reports_errors(setup):
    client, _ = setup
    r = client.post("/api/refresh").json()
    assert r["new"] == 1 and r["fetched"] == 2
    assert r["errors"] == {"Broken": "ConnectError: down"}
    data = client.get("/api/articles?view=today").json()
    assert [a["title"] for a in data["articles"]] == ["Hello"]
    assert data["counts"]["today"] == 1


def test_non_forced_refresh_skips_fresh_feeds(setup):
    client, calls = setup
    client.post("/api/refresh")
    client.post("/api/refresh")
    client.post("/api/refresh?force=true")
    assert calls == [["Good", "Broken"], [], ["Good", "Broken"]]


def test_flags_and_validation(setup):
    client, _ = setup
    client.post("/api/refresh")
    aid = client.get("/api/articles").json()["articles"][0]["id"]
    assert client.post(f"/api/articles/{aid}/saved", json={"value": True}).status_code == 200
    assert len(client.get("/api/articles?view=saved").json()["articles"]) == 1
    assert client.post("/api/articles/999/read", json={"value": True}).status_code == 404
    assert client.get("/api/articles?view=sports").status_code == 400
    assert client.get("/api/articles?view=markets").status_code == 200   # Crypto & Investing tab
    assert client.get("/api/articles?q=" + "x" * 101).status_code == 422
    assert client.post("/api/articles/read-all", json={"ids": [aid]}).json()["updated"] == 1


def test_detail_fetches_once_then_uses_cache(tmp_path):
    from news.reader import ReaderError
    feeds = tmp_path / "feeds.json"
    feeds.write_text(json.dumps({"feeds": [{"name": "G", "url": "https://g/rss", "category": "world"}]}),
                     encoding="utf-8")
    now = datetime.now(timezone.utc).isoformat()
    arts = [{"link": f"https://g/{i}", "title": f"T{i}", "summary": "s", "source": "G", "category": "world",
             "image": None, "published": now, "author": "Ann", "tags": ["Asia"],
             "feed_text": "Feed para one.\nFeed para two."} for i in (1, 2)]
    reads = []

    def fake_reader(url):
        reads.append(url)
        if url.endswith("/2"):
            raise ReaderError("The site refused the request (403)")
        # The page repeats the headline (with curly quotes) as its first paragraph: the API drops it.
        return {"paragraphs": ["T’1", "Full one.", "Full two."], "author": "Page Author", "date": None, "image": None}

    client = local_client(create_app(feeds, tmp_path / "news.db", fetcher=lambda todo: {"G": (arts, None)},
                                   reader=fake_reader))
    client.post("/api/refresh")
    ids = {a["link"]: a["id"] for a in client.get("/api/articles").json()["articles"]}

    ok = client.get(f"/api/articles/{ids['https://g/1']}/detail").json()
    assert ok["reader"]["ok"] and ok["reader"]["paragraphs"] == ["Full one.", "Full two."]
    assert ok["article"]["tags"] == ["Asia"] and ok["feed_text"] == ["Feed para one.", "Feed para two."]
    assert isinstance(ok["highlights"], list)
    client.get(f"/api/articles/{ids['https://g/1']}/detail")              # cached
    assert reads == ["https://g/1"]

    bad = client.get(f"/api/articles/{ids['https://g/2']}/detail").json()
    assert bad["reader"] == {"ok": False, "error": "The site refused the request (403)"}
    client.get(f"/api/articles/{ids['https://g/2']}/detail")              # failure cached too
    client.get(f"/api/articles/{ids['https://g/2']}/detail?retry=true")   # explicit retry refetches
    assert reads == ["https://g/1", "https://g/2", "https://g/2"]
    assert client.get("/api/articles/999/detail").status_code == 404


def test_detail_survives_extractor_crash(tmp_path):
    feeds = tmp_path / "feeds.json"
    feeds.write_text(json.dumps({"feeds": [{"name": "G", "url": "https://g/rss", "category": "world"}]}),
                     encoding="utf-8")
    now = datetime.now(timezone.utc).isoformat()
    art = {"link": "https://g/1", "title": "T", "summary": "s", "source": "G", "category": "world",
           "image": None, "published": now}

    def boom(url):
        raise RuntimeError("parser bug")

    client = local_client(create_app(feeds, tmp_path / "news.db", fetcher=lambda t: {"G": ([art], None)}, reader=boom))
    client.post("/api/refresh")
    aid = client.get("/api/articles").json()["articles"][0]["id"]
    r = client.get(f"/api/articles/{aid}/detail")
    assert r.status_code == 200 and r.json()["reader"]["ok"] is False


def test_status_and_index(setup):
    client, _ = setup
    client.post("/api/refresh")
    feeds = {f["name"]: f for f in client.get("/api/status").json()["feeds"]}
    assert feeds["Broken"]["error"] == "ConnectError: down" and feeds["Good"]["last_count"] == 1
    page = client.get("/")
    assert page.status_code == 200 and "News Forum" in page.text
    assert client.get("/static/app.js").status_code == 200


def test_stories_older_than_the_window_are_skipped(tmp_path):
    from datetime import timedelta
    from news import config
    from news.store import keep_cutoff
    feeds = tmp_path / "feeds.json"
    feeds.write_text(json.dumps({"feeds": [{"name": "G", "url": "https://g/rss", "category": "world"}]}),
                     encoding="utf-8")
    now = datetime.now(timezone.utc)
    cutoff = keep_cutoff(config.KEEP_DAYS)   # midnight starting yesterday, local time
    stamps = {"now": now, "just inside": cutoff + timedelta(minutes=1),
              "just outside": cutoff - timedelta(minutes=1), "10 days old": now - timedelta(days=10)}
    arts = [{"link": f"https://g/{i}", "title": t, "summary": "", "source": "G", "category": "world",
             "image": None, "published": ts.isoformat()} for i, (t, ts) in enumerate(stamps.items())]
    client = local_client(create_app(feeds, tmp_path / "news.db", fetcher=lambda todo: {"G": (arts, None)}))
    assert client.post("/api/refresh").json()["new"] == 2
    titles = [a["title"] for a in client.get("/api/articles?view=world").json()["articles"]]
    assert titles == ["now", "just inside"]


def test_page_files_are_revalidated_so_edits_show_on_refresh(setup):
    client, _ = setup
    for path in ("/", "/static/style.css", "/static/app.js"):
        assert client.get(path).headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/api/status").headers


def test_requests_for_other_host_names_are_refused(setup):
    # DNS rebinding: another site's name pointed at 127.0.0.1 must not be able to read the list.
    client, _ = setup
    assert client.get("/api/status", headers={"host": "evil.example:8770"}).status_code == 400
    assert client.get("/api/status", headers={"host": "localhost:8770"}).status_code == 200


def test_writes_from_other_sites_are_refused(setup):
    client, calls = setup
    client.post("/api/refresh")
    aid = client.get("/api/articles").json()["articles"][0]["id"]
    for origin in ("https://evil.example", "http://localhost:3000", "null"):
        r = client.post(f"/api/articles/{aid}/saved", json={"value": True}, headers={"origin": origin})
        assert r.status_code == 403
        assert client.post("/api/refresh?force=true", headers={"origin": origin}).status_code == 403
    assert client.get("/api/articles?view=saved").json()["articles"] == []
    assert len(calls) == 1
    # The page itself (same origin) and tools that send no Origin still work.
    assert client.post(f"/api/articles/{aid}/saved", json={"value": True},
                       headers={"origin": BASE}).status_code == 200
    assert client.post("/api/refresh?force=true").status_code == 200
