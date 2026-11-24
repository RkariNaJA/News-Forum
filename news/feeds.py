"""Load the feed list, download RSS/Atom feeds and turn entries into article dicts."""
from __future__ import annotations

import calendar
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx

from .config import CATEGORIES

# Not "Mozilla/...": the Guardian refuses (403) a browser-looking UA sent from a non-browser client.
USER_AGENT = "NewsForum/1.0 (personal RSS reader)"
TIMEOUT = 20.0
SUMMARY_MAX = 320        # card blurb
FEED_TEXT_MAX = 6000     # full feed text kept for the reader pop-up
AUTHOR_MAX = 120
TAG_MAX = 40
MAX_TAGS = 6
_BLOCK_RE = re.compile(r"<\s*(?:br\s*/?|/\s*(?:p|div|li|h[1-6]|blockquote))\s*>", re.I)

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_TRACKING_PREFIXES = ("utm_", "at_", "ito", "cmpid", "taid", "__source")


def load_feeds(path: Path) -> list[dict]:
    """Read feeds.json and keep only well-formed http(s) feeds with a known category."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    feeds = []
    for f in data.get("feeds", []):
        name, url, cat = f.get("name"), f.get("url"), f.get("category")
        if not (isinstance(name, str) and isinstance(url, str) and cat in CATEGORIES):
            continue
        if urlsplit(url).scheme not in ("http", "https"):
            continue
        feeds.append({"name": name.strip(), "url": url.strip(), "category": cat})
    return feeds


def clean_text(value: str | None, limit: int | None = None) -> str:
    """Strip HTML tags and entities, collapse whitespace, optionally truncate on a word."""
    if not value:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", value))
    text = _SPACE_RE.sub(" ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return text


def normalize_link(link: str | None) -> str | None:
    """Return a canonical http(s) link without tracking params, or None if unsafe/invalid."""
    if not link:
        return None
    parts = urlsplit(link.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith(_TRACKING_PREFIXES)]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path, urlencode(query), ""))


UNDATED_STEP = timedelta(minutes=20)
UNDATED_MAX = 15   # an undated feed (Nikkei Asia lists 50) would otherwise crowd out its whole tab


def _entry_time(entry, now: datetime) -> datetime | None:
    """The entry's own publish time (capped at now), or None if the feed gives none."""
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            try:
                dt = datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)
                return min(dt, now)  # never in the future
            except (OverflowError, ValueError, TypeError):
                pass
    return None


def _entry_image(entry) -> str | None:
    candidates = []
    for key in ("media_thumbnail", "media_content"):
        for m in entry.get(key) or []:
            candidates.append(m.get("url"))
    for enc in entry.get("enclosures") or []:
        if str(enc.get("type", "")).startswith("image/"):
            candidates.append(enc.get("href") or enc.get("url"))
    for url in candidates:
        if url and urlsplit(url).scheme in ("http", "https"):
            return url
    return None


def parse_feed(content: bytes, feed: dict, now: datetime | None = None) -> list[dict]:
    """Parse raw feed bytes into article dicts for one configured feed."""
    now = now or datetime.now(timezone.utc)
    parsed = feedparser.parse(content)
    articles = []
    undated = 0
    for entry in parsed.entries:
        link = normalize_link(entry.get("link"))
        title = clean_text(entry.get("title"))
        if not link or not title:
            continue
        published = _entry_time(entry, now)
        if published is None:
            # Undated feeds (e.g. Nikkei Asia) list newest first: keep only the newest few, and
            # spread them out in feed order so a first fetch doesn't stack them all at "just now".
            if undated >= UNDATED_MAX:
                continue
            published = now - undated * UNDATED_STEP
            undated += 1
        summary_html = entry.get("summary") or entry.get("description") or ""
        articles.append({
            "link": link,
            "title": title,
            "summary": clean_text(summary_html, SUMMARY_MAX),
            "source": feed["name"],
            "category": feed["category"],
            "image": _entry_image(entry),
            "published": published.isoformat(),
            "author": clean_text(entry.get("author"), AUTHOR_MAX) or None,
            "tags": _entry_tags(entry),
            "feed_text": _feed_text(entry, summary_html),
        })
    return articles


def _entry_tags(entry) -> list[str]:
    tags = []
    for t in entry.get("tags") or []:
        term = clean_text(t.get("term") or t.get("label"), TAG_MAX)
        if term and term.lower() not in {x.lower() for x in tags}:
            tags.append(term)
        if len(tags) >= MAX_TAGS:
            break
    return tags


def paragraphs_from_html(value: str | None) -> list[str]:
    """Split feed HTML into plain-text paragraphs (block tags and <br> become breaks)."""
    if not value:
        return []
    text = _BLOCK_RE.sub("\n", value)
    return [p for p in (clean_text(chunk) for chunk in text.split("\n")) if p]


def _feed_text(entry, summary_html: str) -> str:
    """The richest text the feed itself carries (full content when offered, else the summary)."""
    candidates = [" ".join(c.get("value", "") for c in entry.get("content") or []), summary_html]
    best = max((paragraphs_from_html(c) for c in candidates), key=lambda ps: sum(map(len, ps)))
    out, total = [], 0
    for p in best:
        out.append(p)
        total += len(p)
        if total >= FEED_TEXT_MAX:
            break
    return "\n".join(out)


def describe_error(exc: httpx.HTTPError) -> str:
    """A short, plain message for the banner and Source status: says whether the site refused us,
    the feed moved, or the network failed (these need different fixes)."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403, 451):
            return f"Refused by the site ({code})"
        if code in (404, 410):
            return f"Feed moved or removed ({code})"
        if code == 429:
            return f"Too many requests, the site asked us to slow down ({code})"
        if code >= 500:
            return f"The site is having problems ({code})"
        return f"The site returned an error ({code})"
    if isinstance(exc, httpx.TimeoutException):
        return "Timed out"
    if isinstance(exc, httpx.ConnectError):
        return "Couldn't find the site" if "getaddrinfo" in str(exc) else "Couldn't connect (network or firewall)"
    if isinstance(exc, httpx.TooManyRedirects):
        return "Too many redirects"
    return f"Network error ({type(exc).__name__})"


def fetch_feed(feed: dict, client: httpx.Client) -> tuple[list[dict], str | None]:
    """Download and parse one feed. Returns (articles, error message or None)."""
    try:
        resp = client.get(feed["url"])
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        # the raw text goes to the log (data/news-forum.log when windowless) for debugging
        print(f"Feed {feed['name']}: {type(exc).__name__}: {str(exc)[:300]}", flush=True)
        return [], describe_error(exc)
    articles = parse_feed(resp.content, feed)
    if not articles:
        return [], "No readable stories in the feed (its format may have changed)"
    return articles, None


def fetch_all(feeds: list[dict], workers: int = 8) -> dict[str, tuple[list[dict], str | None]]:
    """Fetch several feeds in parallel. One broken feed never stops the others."""
    results: dict[str, tuple[list[dict], str | None]] = {}
    if not feeds:
        return results
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": USER_AGENT}) as client:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {f["name"]: pool.submit(fetch_feed, f, client) for f in feeds}
            for name, fut in futures.items():
                try:
                    results[name] = fut.result()
                except Exception as exc:  # parser bugs etc. must not crash a refresh
                    results[name] = ([], f"{type(exc).__name__}: {str(exc)[:150]}")
    return results
