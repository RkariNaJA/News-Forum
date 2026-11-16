"""SQLite storage for articles, per-feed fetch status and the reader-view cache."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    link      TEXT NOT NULL UNIQUE,
    title     TEXT NOT NULL,
    summary   TEXT NOT NULL DEFAULT '',
    source    TEXT NOT NULL,
    category  TEXT NOT NULL,
    image     TEXT,
    published TEXT NOT NULL,
    fetched   TEXT NOT NULL,
    is_read   INTEGER NOT NULL DEFAULT 0,
    saved     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_articles_published ON articles(published);
CREATE INDEX IF NOT EXISTS ix_articles_category  ON articles(category, published);
CREATE TABLE IF NOT EXISTS feed_status (
    name       TEXT PRIMARY KEY,
    url        TEXT NOT NULL,
    category   TEXT NOT NULL,
    last_fetch TEXT,
    last_ok    TEXT,
    error      TEXT,
    last_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reader_cache (
    article_id INTEGER PRIMARY KEY,
    fetched    TEXT NOT NULL,
    ok         INTEGER NOT NULL,
    data       TEXT,          -- JSON: paragraphs, author, date, image (when ok)
    error      TEXT
);
"""

# Columns added after the first release; created on old databases by _migrate().
EXTRA_COLUMNS = {"author": "TEXT", "tags": "TEXT", "feed_text": "TEXT"}
READER_RETRY = timedelta(hours=6)   # a failed extraction is retried after this

LIST_LIMIT = 400


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)
            have = {r["name"] for r in c.execute("PRAGMA table_info(articles)")}
            for col, typ in EXTRA_COLUMNS.items():
                if col not in have:
                    c.execute(f"ALTER TABLE articles ADD COLUMN {col} {typ}")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- writes -------------------------------------------------------
    def add_articles(self, articles: list[dict], now: datetime | None = None) -> int:
        """Insert new articles; links already stored keep their row (and read/saved flags).
        Returns how many were new. Older rows missing the detail fields get them filled in."""
        fetched = (now or _now()).isoformat()
        rows = [(a["link"], a["title"], a.get("summary", ""), a["source"], a["category"],
                 a.get("image"), a["published"], fetched, a.get("author"),
                 json.dumps(a.get("tags") or []), a.get("feed_text") or "") for a in articles]
        with self._lock, self._conn() as c:
            before = c.total_changes
            c.executemany(
                "INSERT OR IGNORE INTO articles (link, title, summary, source, category, image,"
                " published, fetched, author, tags, feed_text) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
            new = c.total_changes - before
            c.executemany(
                "UPDATE articles SET author=?, tags=?, feed_text=?"
                " WHERE link=? AND COALESCE(feed_text, '') = ''",
                [(r[8], r[9], r[10], r[0]) for r in rows if r[10]])
            return new

    def set_flag(self, article_id: int, flag: str, value: bool) -> bool:
        if flag not in ("is_read", "saved"):
            raise ValueError(f"unknown flag {flag!r}")
        with self._lock, self._conn() as c:
            cur = c.execute(f"UPDATE articles SET {flag}=? WHERE id=?", (int(value), article_id))
            return cur.rowcount == 1

    def mark_all_read(self, ids: list[int]) -> int:
        if not ids:
            return 0
        with self._lock, self._conn() as c:
            cur = c.executemany("UPDATE articles SET is_read=1 WHERE id=?", [(i,) for i in ids])
            return cur.rowcount

    def prune(self, keep_days: int, now: datetime | None = None) -> int:
        """Delete unsaved articles older than keep_days. Saved articles are kept forever."""
        cutoff = ((now or _now()) - timedelta(days=keep_days)).isoformat()
        with self._lock, self._conn() as c:
            cur = c.execute("DELETE FROM articles WHERE saved=0 AND published < ?", (cutoff,))
            c.execute("DELETE FROM reader_cache WHERE article_id NOT IN (SELECT id FROM articles)")
            return cur.rowcount

    def record_fetch(self, feed: dict, count: int, error: str | None,
                     now: datetime | None = None) -> None:
        ts = (now or _now()).isoformat()
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO feed_status (name, url, category, last_fetch, last_ok, error, last_count)"
                " VALUES (?,?,?,?,?,?,?)"
                " ON CONFLICT(name) DO UPDATE SET url=excluded.url, category=excluded.category,"
                " last_fetch=excluded.last_fetch, error=excluded.error, last_count=excluded.last_count,"
                " last_ok=COALESCE(excluded.last_ok, feed_status.last_ok)",
                (feed["name"], feed["url"], feed["category"], ts,
                 None if error else ts, error, count))

    # ---- reads --------------------------------------------------------
    def list_articles(self, view: str = "today", q: str | None = None,
                      now: datetime | None = None, limit: int = LIST_LIMIT) -> list[dict]:
        """view: 'today' (last 24h, all categories), a category name, or 'saved'."""
        where, params = [], []
        if view == "today":
            where.append("published >= ?")
            params.append(((now or _now()) - timedelta(hours=24)).isoformat())
        elif view == "saved":
            where.append("saved = 1")
        else:
            where.append("category = ?")
            params.append(view)
        if q:
            where.append("(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\')")
            like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            params += [like, like]
        sql = ("SELECT id, link, title, summary, source, category, image, published, is_read, saved"
               " FROM articles WHERE " + " AND ".join(where) +
               " ORDER BY published DESC, id DESC LIMIT ?")
        params.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(sql, params)]

    def get_article(self, article_id: int) -> dict | None:
        """One article with every stored field (tags decoded), or None."""
        with self._conn() as c:
            row = c.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
        if row is None:
            return None
        art = dict(row)
        try:
            art["tags"] = json.loads(art.get("tags") or "[]")
        except ValueError:
            art["tags"] = []
        art["feed_text"] = art.get("feed_text") or ""
        return art

    def corpus_state(self) -> tuple[int, int]:
        """(row count, highest id): changes whenever articles are added or trimmed."""
        with self._conn() as c:
            return tuple(c.execute("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM articles").fetchone())

    def corpus_texts(self) -> list[str]:
        """Title + blurb + feed text of every stored story, for the highlight document frequencies."""
        with self._conn() as c:
            return [" ".join(filter(None, r)) for r in
                    c.execute("SELECT title, summary, feed_text FROM articles")]

    def get_reader(self, article_id: int, now: datetime | None = None) -> dict | None:
        """Cached reader result: {'ok': True, ...data} or {'ok': False, 'error'}.
        None when nothing is cached or a failure is old enough to retry."""
        with self._conn() as c:
            row = c.execute("SELECT * FROM reader_cache WHERE article_id=?", (article_id,)).fetchone()
        if row is None:
            return None
        if row["ok"]:
            return {"ok": True, **json.loads(row["data"])}
        if datetime.fromisoformat(row["fetched"]) < (now or _now()) - READER_RETRY:
            return None
        return {"ok": False, "error": row["error"]}

    def save_reader(self, article_id: int, data: dict | None, error: str | None,
                    now: datetime | None = None) -> None:
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO reader_cache (article_id, fetched, ok, data, error)"
                      " VALUES (?,?,?,?,?)",
                      (article_id, (now or _now()).isoformat(), int(data is not None),
                       json.dumps(data) if data is not None else None, error))

    def feed_statuses(self) -> dict[str, dict]:
        with self._conn() as c:
            return {r["name"]: dict(r) for r in c.execute("SELECT * FROM feed_status")}

    def counts(self, now: datetime | None = None) -> dict[str, int]:
        """Unread counts per tab."""
        since = ((now or _now()) - timedelta(hours=24)).isoformat()
        with self._conn() as c:
            out = {r["category"]: r["n"] for r in c.execute(
                "SELECT category, COUNT(*) n FROM articles WHERE is_read=0 GROUP BY category")}
            out["today"] = c.execute(
                "SELECT COUNT(*) FROM articles WHERE is_read=0 AND published >= ?", (since,)
            ).fetchone()[0]
            out["saved"] = c.execute("SELECT COUNT(*) FROM articles WHERE saved=1").fetchone()[0]
        return out
