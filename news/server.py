"""FastAPI app: serves the reader page and a small JSON API."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

from . import config
from .etf import BtcEtf
from .feargreed import FearGreed
from .fedwatch import FedWatch
from .feeds import fetch_all, load_feeds
from .highlights import Corpus, key_sentences
from .reader import ReaderError, read_article, same_text
from .store import Store, keep_cutoff

VIEWS = ("today", "saved") + config.CATEGORIES


class FlagBody(BaseModel):
    value: bool


class IdsBody(BaseModel):
    ids: list[int] = Field(default_factory=list, max_length=1000)


def create_app(feeds_path: Path, db_path: Path,
               fetcher: Callable[[list[dict]], dict] = fetch_all,
               reader: Callable[[str], dict] = read_article, fedwatch: FedWatch | None = None,
               feargreed: FearGreed | None = None, etf: BtcEtf | None = None) -> FastAPI:
    app = FastAPI(title="News Forum")
    store = Store(db_path)
    fedwatch = fedwatch or FedWatch()
    feargreed = feargreed or FearGreed()
    etf = etf or BtcEtf()
    refresh_lock = threading.Lock()
    corpus_cache: dict = {"state": None, "corpus": None}
    corpus_lock = threading.Lock()

    def corpus() -> Corpus:
        """Document frequencies over all stored stories; rebuilt only when the stories change."""
        with corpus_lock:
            state = store.corpus_state()
            if corpus_cache["state"] != state:
                corpus_cache["corpus"] = Corpus(store.corpus_texts())
                corpus_cache["state"] = state
            return corpus_cache["corpus"]

    def stale_feeds(feeds: list[dict], force: bool) -> list[dict]:
        if force:
            return feeds
        statuses = store.feed_statuses()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=config.STALE_MINUTES)
        out = []
        for f in feeds:
            last = statuses.get(f["name"], {}).get("last_fetch")
            if not last or datetime.fromisoformat(last) < cutoff:
                out.append(f)
        return out

    @app.post("/api/refresh")
    def refresh(force: bool = False):
        feeds = load_feeds(feeds_path)
        # Only one refresh at a time; a second caller just reports "busy".
        if not refresh_lock.acquire(blocking=False):
            return {"busy": True, "fetched": 0, "new": 0, "errors": {}}
        try:
            todo = stale_feeds(feeds, force)
            results = fetcher(todo)
            new, errors = 0, {}
            # Feeds often carry stories older than the window; don't store them only to trim them again.
            cutoff = keep_cutoff(config.KEEP_DAYS).isoformat()
            for f in todo:
                articles, err = results.get(f["name"], ([], "No result"))
                new += store.add_articles([a for a in articles if a["published"] >= cutoff])
                store.record_fetch(f, len(articles), err)
                if err:
                    errors[f["name"]] = err
            pruned = store.prune(config.KEEP_DAYS)
            return {"busy": False, "fetched": len(todo), "new": new,
                    "pruned": pruned, "errors": errors}
        finally:
            refresh_lock.release()

    @app.get("/api/articles")
    def articles(view: str = "today", q: str | None = Query(None, max_length=100)):
        if view not in VIEWS:
            raise HTTPException(400, f"view must be one of {', '.join(VIEWS)}")
        return {"view": view, "articles": store.list_articles(view, (q or "").strip() or None),
                "counts": store.counts()}

    @app.get("/api/counts")
    def counts():
        """Unread counts per tab, without the stories (for the tab badges)."""
        return store.counts()

    @app.post("/api/articles/{article_id}/read")
    def set_read(article_id: int, body: FlagBody):
        if not store.set_flag(article_id, "is_read", body.value):
            raise HTTPException(404, "article not found")
        return {"ok": True, "counts": store.counts()}

    @app.post("/api/articles/{article_id}/saved")
    def set_saved(article_id: int, body: FlagBody):
        if not store.set_flag(article_id, "saved", body.value):
            raise HTTPException(404, "article not found")
        return {"ok": True, "counts": store.counts()}

    @app.get("/api/articles/{article_id}/detail")
    def detail(article_id: int, retry: bool = False):
        """Everything for the reader pop-up. The article page is fetched once, then cached."""
        art = store.get_article(article_id)
        if art is None:
            raise HTTPException(404, "article not found")
        cached = store.get_reader(article_id)
        if cached is None or (retry and not cached["ok"]):
            try:
                data = reader(art["link"])
                store.save_reader(article_id, data, None)
                cached = {"ok": True, **data}
            except ReaderError as exc:
                store.save_reader(article_id, None, str(exc))
                cached = {"ok": False, "error": str(exc)}
            except Exception as exc:  # extractor bugs must not break the pop-up
                cached = {"ok": False, "error": f"Couldn't read this page ({type(exc).__name__})"}
        feed_text = [p for p in art.pop("feed_text").splitlines() if p]
        art.pop("fetched", None)
        # The pop-up shows its own headline: drop a first paragraph that just repeats it.
        if cached["ok"] and cached["paragraphs"] and same_text(cached["paragraphs"][0], art["title"]):
            cached = {**cached, "paragraphs": cached["paragraphs"][1:]}
        shown = (cached.get("paragraphs") if cached["ok"] else None) or feed_text or [art["summary"]]
        highlights = key_sentences(art["title"], shown, corpus(),
                                   exclude=[art["source"], art.get("author") or "", cached.get("author") or ""])
        return {"article": art, "feed_text": feed_text, "reader": cached, "highlights": highlights}

    @app.post("/api/articles/read-all")
    def read_all(body: IdsBody):
        return {"updated": store.mark_all_read(body.ids), "counts": store.counts()}

    @app.get("/api/status")
    def status():
        feeds = load_feeds(feeds_path)
        statuses = store.feed_statuses()
        return {"feeds": [{**f, **{k: statuses.get(f["name"], {}).get(k)
                                   for k in ("last_fetch", "last_ok", "error", "last_count")}}
                          for f in feeds]}

    @app.get("/api/fedwatch")
    def fed_watch():
        """Next FOMC decision, upcoming meetings, today's target range and the futures-implied odds."""
        return fedwatch.snapshot()

    @app.get("/api/feargreed")
    def fear_greed():
        """Crypto Fear & Greed Index: today's value and the daily history (alternative.me)."""
        return feargreed.snapshot()

    @app.get("/api/etf")
    def btc_etf():
        """US spot Bitcoin ETFs: each fund's latest figures and the daily totals (SoSoValue, needs a key)."""
        return etf.snapshot()

    @app.get("/")
    def index():
        return FileResponse(config.WEB_DIR / "index.html")

    @app.middleware("http")
    async def revalidate_page_files(request, call_next):
        """Make the browser re-check the page, CSS and JS on every load, so edits show on a plain refresh."""
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.middleware("http")
    async def same_origin_writes(request, call_next):
        """Refuse writes sent by another site's page open in the same browser. Browsers always add
        Origin to a cross-site POST; tools such as curl send none and are allowed."""
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin is not None:
            if urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower():
                return JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
        return await call_next(request)

    # Added last, so it runs first: a request addressed to any other host name is refused outright.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(config.ALLOWED_HOSTS))

    app.mount("/static", StaticFiles(directory=config.WEB_DIR), name="static")
    return app
