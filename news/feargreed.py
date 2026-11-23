"""Crypto Fear & Greed Index for the Crypto Prices page.

TradingView has no Fear & Greed symbol, so this reads alternative.me's free API (no key): one value a
day, 0 = extreme fear to 100 = extreme greed, with the full history back to February 2018.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Callable

import httpx

FNG_URL = "https://api.alternative.me/fng/?limit=0"   # limit=0: the whole history, newest first
SOURCE_URL = "https://alternative.me/crypto/fear-and-greed-index/"
TIMEOUT = 15.0
TTL = 3600            # the index changes once a day; re-read at most hourly
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsForum/1.0 (personal RSS reader)"


class FearGreedError(Exception):
    """The index could not be read; the message is short and shown on the page."""


def parse(payload: dict, now: float | None = None) -> dict:
    """alternative.me's JSON -> {"current": {date, value, label}, "history": [[date, value], ...] oldest
    first, "next_update": ISO time of the next value or None}."""
    try:
        rows = payload["data"]
        history = sorted((datetime.fromtimestamp(int(r["timestamp"]), timezone.utc).date().isoformat(),
                          int(r["value"])) for r in rows)
        newest = max(rows, key=lambda r: int(r["timestamp"]))
        label = str(newest["value_classification"])
        wait = newest.get("time_until_update")
    except (KeyError, TypeError, ValueError) as exc:
        raise FearGreedError("alternative.me's data has changed") from exc
    if not history:
        raise FearGreedError("alternative.me returned no values")
    next_update = None
    if wait not in (None, ""):
        next_update = datetime.fromtimestamp((now or time.time()) + int(wait), timezone.utc).isoformat()
    date, value = history[-1]
    return {"current": {"date": date, "value": value, "label": label},
            "history": [list(h) for h in history], "next_update": next_update}


def fetch() -> dict:
    try:
        r = httpx.get(FNG_URL, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        payload = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise FearGreedError(f"Couldn't reach alternative.me ({type(exc).__name__})") from exc
    return parse(payload)


class FearGreed:
    """Reuses the last answer for TTL seconds, and keeps showing it if a later fetch fails."""

    def __init__(self, get: Callable[[], dict] = fetch, clock: Callable[[], float] = time.time):
        self._get, self._clock = get, clock
        self._hit: tuple[float, dict] | None = None
        self._lock = threading.Lock()

    def snapshot(self) -> dict:
        with self._lock:
            hit = self._hit
        if hit is None or self._clock() - hit[0] >= TTL:
            try:
                data = self._get()
                with self._lock:
                    self._hit = hit = (self._clock(), data)
            except FearGreedError as exc:
                if hit is None:
                    return {"current": None, "history": [], "next_update": None, "error": str(exc),
                            "source_url": SOURCE_URL}
        return {**hit[1], "error": None, "source_url": SOURCE_URL}
