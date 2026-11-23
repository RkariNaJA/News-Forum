"""FedWatch page: the next FOMC decision and the market's odds for it.

CME's own FedWatch tool can't be embedded (its page and data server refuse other sites), so the odds
are worked out here with CME's published method, from CBOT 30-Day Fed Funds futures:

- A futures contract settles on 100 minus the month's average effective fed funds rate (EFFR).
- In the meeting month, the rate before the decision holds for d days and the new one for N - d.
  If the month before has no meeting, its contract gives the rate at the start of the meeting month;
  the meeting month's contract then gives the rate after the decision. If the month before has a
  meeting but the month after doesn't, the month after gives the end rate instead.
- The implied move, in 25 bp steps, is split between the two nearest whole steps: e.g. -0.78
  steps = 78 % odds of a 25 bp cut, 22 % of no change.

Sources (all free, no key): the Fed's FOMC calendar page, the New York Fed's EFFR API (today's target
range) and Yahoo Finance's chart API (delayed futures quotes).
"""
from __future__ import annotations

import calendar
import math
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

import httpx

CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
EFFR_URL = "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/1.json"
QUOTE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
CME_FEDWATCH_URL = "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
TIMEOUT = 15.0
ET = ZoneInfo("America/New_York")
DECISION_HOUR_ET = 14          # the statement comes out at 2:00 pm Eastern on the meeting's last day
STEP = 0.25                    # the Fed moves in 25 bp steps
UPCOMING_SHOWN = 8

# How long each answer is reused before it is fetched again (seconds).
CALENDAR_TTL = 24 * 3600
RATE_TTL = 3 * 3600
QUOTE_TTL = 10 * 60

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
FUTURES_CODES = "FGHJKMNQUVXZ"   # CME month codes, January to December

_YEAR_RE = re.compile(r'<h4><a id="\d+">(\d{4}) FOMC Meetings</a></h4>')
_MONTH_RE = re.compile(r'fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>')
_DATE_RE = re.compile(r'fomc-meeting__date[^>]*>([^<]+)<')
_DAYS_RE = re.compile(r"^(\d{1,2})(?:-(\d{1,2}))?(\*)?$")


class FedWatchError(Exception):
    """A source could not be read; the message is short and shown on the page."""


# ---- FOMC calendar ----------------------------------------------------------------------------
def parse_calendar(html: str) -> list[dict]:
    """Every scheduled meeting on the Fed's calendar page, oldest first:
    {"date": last day (YYYY-MM-DD), "label": "8-9 Dec", "sep": bool, "decision": ISO UTC time}.
    Notation votes and unscheduled meetings are left out."""
    meetings = []
    parts = _YEAR_RE.split(html)            # [before, year, section, year, section, ...]
    for year, section in zip(parts[1::2], parts[2::2]):
        months, days = _MONTH_RE.findall(section), _DATE_RE.findall(section)
        for month_text, day_text in zip(months, days):
            m = _DAYS_RE.match(day_text.strip())
            names = [x.strip().lower() for x in month_text.split("/")]
            if not m or not all(n in MONTHS for n in names):
                continue
            first, last, sep = int(m.group(1)), int(m.group(2) or m.group(1)), bool(m.group(3))
            month = MONTHS[names[-1]] if last < first else MONTHS[names[0]]   # "Apr/May 30-1" ends in May
            try:
                day = date(int(year), month, last)
            except ValueError:
                continue
            short = calendar.month_abbr[month] if len(names) == 1 else "/".join(n[:3].title() for n in names)
            meetings.append({"date": day.isoformat(), "label": f"{day_text.strip().rstrip('*')} {short}",
                             "sep": sep, "decision": decision_time(day).isoformat()})
    return sorted({m["date"]: m for m in meetings}.values(), key=lambda m: m["date"])


def decision_time(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, DECISION_HOUR_ET, tzinfo=ET).astimezone(timezone.utc)


# ---- odds ---------------------------------------------------------------------------------------
def contract(year: int, month: int) -> str:
    """CME symbol of the 30-Day Fed Funds future for a month, e.g. ZQZ26 for December 2026."""
    return f"ZQ{FUTURES_CODES[month - 1]}{year % 100:02d}"


def _shift(year: int, month: int, by: int) -> tuple[int, int]:
    i = year * 12 + month - 1 + by
    return i // 12, i % 12 + 1


def meeting_rates(day: date, meeting_months: set[tuple[int, int]],
                  price: Callable[[str], float], spot: float) -> tuple[float, float, str]:
    """Rate before and after the meeting implied by the futures, and which price anchored it."""
    n = calendar.monthrange(day.year, day.month)[1]
    d = day.day                           # days at the old rate; the new one starts the next day
    avg = 100 - price(contract(day.year, day.month))
    prev, nxt = _shift(day.year, day.month, -1), _shift(day.year, day.month, 1)
    if d >= n:                            # decided on the month's last day: the new rate starts next month
        return avg, 100 - price(contract(*nxt)), "next month"
    if prev not in meeting_months:
        start = 100 - price(contract(*prev))
        return start, (avg * n - start * d) / (n - d), "previous month"
    if nxt not in meeting_months:
        end = 100 - price(contract(*nxt))
        return (avg * n - end * (n - d)) / d, end, "next month"
    return spot, (avg * n - spot * d) / (n - d), "today's rate"


def outcome_odds(start: float, end: float, low: float, high: float) -> list[dict]:
    """Split the implied move between the two nearest 25 bp steps, as target ranges with odds."""
    steps = (end - start) / STEP
    below = math.floor(steps + 1e-9)
    upper = min(1.0, max(0.0, steps - below))
    out = []
    for k, p in ((below, 1 - upper), (below + 1, upper)):
        if p > 0.0005:
            out.append({"move_bp": round(k * 25), "low": round(low + k * STEP, 2),
                        "high": round(high + k * STEP, 2), "prob": round(p, 4)})
    return sorted(out, key=lambda o: o["low"])


# ---- fetching -----------------------------------------------------------------------------------
def _get(url: str) -> httpx.Response:
    try:
        r = httpx.get(url, timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        return r
    except httpx.HTTPError as exc:
        raise FedWatchError(f"Couldn't reach {httpx.URL(url).host} ({type(exc).__name__})") from exc


def fetch_calendar() -> list[dict]:
    meetings = parse_calendar(_get(CALENDAR_URL).text)
    if not meetings:
        raise FedWatchError("The Fed's calendar page has changed: no meetings found")
    return meetings


def fetch_rate() -> dict:
    try:
        r = _get(EFFR_URL).json()["refRates"][0]
        return {"low": float(r["targetRateFrom"]), "high": float(r["targetRateTo"]),
                "effr": float(r["percentRate"]), "as_of": r["effectiveDate"]}
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise FedWatchError("The New York Fed's rate data has changed") from exc


def fetch_quote(symbol: str) -> dict:
    """Last price of one futures contract (Yahoo's symbol adds .CBT), with its time."""
    try:
        meta = _get(QUOTE_URL.format(symbol=f"{symbol}.CBT")).json()["chart"]["result"][0]["meta"]
        return {"symbol": symbol, "price": float(meta["regularMarketPrice"]),
                "time": datetime.fromtimestamp(meta["regularMarketTime"], timezone.utc).isoformat()}
    except FedWatchError:
        raise
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise FedWatchError(f"No price for {symbol}") from exc


class FedWatch:
    """Builds the page's data, reusing each source's last answer for a while (see the *_TTL values).
    When a source fails, its last good answer is used if there is one."""

    def __init__(self, get_calendar=fetch_calendar, get_rate=fetch_rate, get_quote=fetch_quote,
                 clock: Callable[[], float] = time.time):
        self._sources = {"calendar": (get_calendar, CALENDAR_TTL), "rate": (get_rate, RATE_TTL)}
        self._get_quote = get_quote
        self._clock = clock
        self._cache: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def _cached(self, key: str, fetch: Callable[[], object], ttl: float):
        with self._lock:
            hit = self._cache.get(key)
        if hit and self._clock() - hit[0] < ttl:
            return hit[1]
        try:
            value = fetch()
        except FedWatchError:
            if hit:
                return hit[1]
            raise
        with self._lock:
            self._cache[key] = (self._clock(), value)
        return value

    def snapshot(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        out: dict = {"next": None, "upcoming": [], "target": None, "odds": None, "errors": {},
                     "cme_url": CME_FEDWATCH_URL}
        try:
            meetings = self._cached("calendar", *self._sources["calendar"])
        except FedWatchError as exc:
            out["errors"]["calendar"] = str(exc)
            return out
        upcoming = [m for m in meetings if datetime.fromisoformat(m["decision"]) > now]
        if not upcoming:
            out["errors"]["calendar"] = "No upcoming meetings on the Fed's calendar yet"
            return out
        out["next"], out["upcoming"] = upcoming[0], upcoming[1:1 + UPCOMING_SHOWN]
        try:
            out["target"] = self._cached("rate", *self._sources["rate"])
        except FedWatchError as exc:
            out["errors"]["rate"] = str(exc)
            return out
        try:
            out["odds"] = self._odds(upcoming[0], meetings, out["target"])
        except FedWatchError as exc:
            out["errors"]["futures"] = str(exc)
        return out

    def _odds(self, meeting: dict, meetings: list[dict], target: dict) -> dict:
        day = date.fromisoformat(meeting["date"])
        months = {(date.fromisoformat(m["date"]).year, date.fromisoformat(m["date"]).month) for m in meetings}
        used: dict[str, dict] = {}

        def price(symbol: str) -> float:
            used[symbol] = self._cached(f"quote:{symbol}", lambda: self._get_quote(symbol), QUOTE_TTL)
            return used[symbol]["price"]

        start, end, anchor = meeting_rates(day, months, price, target["effr"])
        return {"meeting": meeting["date"], "outcomes": outcome_odds(start, end, target["low"], target["high"]),
                "rate_before": round(start, 3), "rate_after": round(end, 3), "anchor": anchor,
                "contracts": sorted(used.values(), key=lambda q: q["symbol"])}
