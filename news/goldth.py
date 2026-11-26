"""Thai gold prices for the Gold TH Price page, from ทองคำราคา.com (xn--42cah7d0cxcvbbb9x.com).

The site has no API: its home page carries the Gold Traders Association's latest announcement (a small
box) and a table of today's announcements, both as plain HTML. Prices are Thai baht for one baht-weight
(15.244 g) of 96.5 % gold. The table can lag the box by one announcement; that newest one is then added
on top from the box, without the spot price and exchange rate the table would have.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Callable

import httpx

SOURCE_URL = "https://xn--42cah7d0cxcvbbb9x.com/"     # ทองคำราคา.com
TIMEOUT = 15.0
TTL = 300             # the association can announce a new price every few minutes on a busy day
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsForum/1.0 (personal RSS reader)"
BANGKOK = timezone(timedelta(hours=7))
THAI_MONTHS = ("มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
               "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม")


class GoldThError(Exception):
    """The prices could not be read; the message is short and shown on the page."""


class _Tables(HTMLParser):
    """Collects every <table> as rows of (text, classes) cells. A cell's classes include those of the
    elements inside it, where the site marks up and down (css-sprite-up, img-down…). `latest` is the
    table inside the announcement box (div.divgta), `rounds` the one with class pdtable."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._stack: list[dict] = []     # open tables (they can nest)
        self._cell: list | None = None   # [text parts, classes]
        self._row: list | None = None
        self._in_box = 0                 # depth inside div.divgta, 0 = outside
        self.latest: dict | None = None
        self.rounds: dict | None = None

    def handle_starttag(self, tag, attrs):
        classes = set((dict(attrs).get("class") or "").split())
        if tag == "div":
            if self._in_box:
                self._in_box += 1
            elif "divgta" in classes:
                self._in_box = 1
        elif tag == "table":
            t = {"rows": [], "classes": classes}
            self.tables.append(t)
            self._stack.append(t)
            if self._in_box and self.latest is None:
                self.latest = t
            if "pdtable" in classes and self.rounds is None:
                self.rounds = t
        elif tag == "tr" and self._stack:
            self._row = []
            self._stack[-1]["rows"].append(self._row)
        elif tag in ("td", "th") and self._row is not None:
            self._cell = [[], set(classes)]
            self._row.append(self._cell)
        elif self._cell is not None:
            self._cell[1] |= classes

    def handle_endtag(self, tag):
        if tag == "div" and self._in_box:
            self._in_box -= 1
        elif tag == "table" and self._stack:
            self._stack.pop()
            self._row = self._cell = None
        elif tag == "tr":
            self._row = self._cell = None
        elif tag in ("td", "th"):
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell[0].append(data)

    def rows(self, table: dict | None) -> list[list[tuple[str, set]]]:
        if table is None:
            return []
        return [[(" ".join("".join(c[0]).split()), c[1]) for c in r] for r in table["rows"]]


def _num(text: str) -> float | None:
    """'57,550.00' -> 57550.0; 'n/a', '' or '-' -> None. Keeps a leading minus."""
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", text)
    return float(m.group(0).replace(",", "")) if m else None


def _signed(text: str, classes: set) -> float | None:
    """A change figure whose direction is shown by an arrow image (img-down, css-sprite-down, g-d)."""
    v = _num(text)
    if v is None:
        return None
    down = any(c.endswith("-down") or c in ("g-d", "goldDown") for c in classes)
    return -abs(v) if down else v


def _thai_year(y: int) -> int:
    return y - 543 if y > 2400 else y      # Buddhist era: 2569 = 2026


def _round_time(text: str) -> str:
    """'26/11/2569 09:54' -> '2026-11-26T09:54:00+07:00'."""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})", text)
    if not m:
        raise ValueError(f"bad time {text!r}")
    d, mo, y, h, mi = map(int, m.groups())
    return datetime(_thai_year(y), mo, d, h, mi, tzinfo=BANGKOK).isoformat()


def _box_time(date_text: str, time_text: str) -> str:
    """'26 พฤศจิกายน 2569', 'เวลา 09:57 น.' -> '2026-11-26T09:57:00+07:00'."""
    m = re.search(r"(\d{1,2})\s+(\S+)\s+(\d{4})", date_text)
    t = re.search(r"(\d{1,2})[:.](\d{2})", time_text)
    if not m or not t or m.group(2) not in THAI_MONTHS:
        raise ValueError(f"bad date {date_text!r} {time_text!r}")
    month = THAI_MONTHS.index(m.group(2)) + 1
    return datetime(_thai_year(int(m.group(3))), month, int(m.group(1)),
                    int(t.group(1)), int(t.group(2)), tzinfo=BANGKOK).isoformat()


def _parse_latest(rows: list) -> dict:
    """The announcement box: [96.5%, buy, sell], [bar, buy, sell], [ornament, buy, sell],
    [today's change, arrow, change since the last announcement], [date, time, (round n)]."""
    bar = next(r for r in rows if r and "ทองคำแท่ง" in r[0][0])
    orn = next(r for r in rows if r and "ทองรูปพรรณ" in r[0][0])
    chg = next(r for r in rows if r and "วันนี้" in r[0][0])
    when = next(r for r in rows if len(r) >= 3 and "ครั้งที่" in r[2][0])
    return {
        "time": _box_time(when[0][0], when[1][0]),
        "round": int(_num(when[2][0])),
        "bar_buy": _num(bar[1][0]), "bar_sell": _num(bar[2][0]),
        "ornament_buy": _num(orn[1][0]), "ornament_sell": _num(orn[2][0]),
        "change_today": _signed(chg[0][0].replace("วันนี้", ""), chg[0][1]),
        "change": _num(chg[2][0]),
    }


def _parse_rounds(rows: list) -> list[dict]:
    """Today's table, newest first: time, round, bar buy, bar sell, ornament buy (the tax base),
    ornament sell, gold spot (USD/oz), baht per US dollar, change since the round before."""
    out = []
    for r in rows:
        if len(r) < 9 or not re.match(r"\d{1,2}/\d{1,2}/\d{4}", r[0][0]):
            continue                    # the two header rows
        out.append({
            "time": _round_time(r[0][0]), "round": int(_num(r[1][0])),
            "bar_buy": _num(r[2][0]), "bar_sell": _num(r[3][0]),
            "ornament_buy": _num(r[4][0]), "ornament_sell": _num(r[5][0]),
            "spot": _num(r[6][0]), "thb": _num(r[7][0]),
            "change": _signed(r[8][0], r[8][1] | r[0][1]),
        })
    return out


def parse(html: str) -> dict:
    """The site's home page -> {"latest": {...}, "rounds": [{...}, ...] newest first}."""
    p = _Tables()
    p.feed(html)
    try:
        latest = _parse_latest(p.rows(p.latest))
        rounds = _parse_rounds(p.rows(p.rounds))
    except (StopIteration, IndexError, TypeError, ValueError) as exc:
        raise GoldThError("ทองคำราคา.com's page has changed") from exc
    if latest["bar_sell"] is None:
        raise GoldThError("ทองคำราคา.com showed no gold price")
    # the table is updated a little after the box: put the newest announcement on top
    same_day = not rounds or rounds[0]["time"][:10] == latest["time"][:10]
    if same_day and (not rounds or latest["round"] > rounds[0]["round"]):
        rounds.insert(0, {**{k: latest[k] for k in ("time", "round", "bar_buy", "bar_sell",
                                                    "ornament_buy", "ornament_sell", "change")},
                          "spot": None, "thb": None})
    return {"latest": latest, "rounds": rounds}


def fetch() -> dict:
    try:
        r = httpx.get(SOURCE_URL, timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise GoldThError(f"Couldn't reach ทองคำราคา.com ({type(exc).__name__})") from exc
    return parse(r.text)


class GoldTh:
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
            except GoldThError as exc:
                if hit is None:
                    return {"latest": None, "rounds": [], "error": str(exc), "source_url": SOURCE_URL}
                # else keep showing the last answer: its announcement time says how old it is
        return {**hit[1], "error": None, "source_url": SOURCE_URL}
