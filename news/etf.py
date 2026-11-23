"""US spot Bitcoin ETF table for the BTC ETF page, from SoSoValue's API.

CoinGlass's ETF page is filled from a private API, so this uses SoSoValue's OpenAPI instead (a free key from
https://sosovalue.com/developer/dashboard). The key comes from the SOSOVALUE_API_KEY environment variable,
or from a SOSOVALUE_API_KEY=... line in the project's .env file (git-ignored). Flows and net assets settle a day late (T+1).
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx

from . import config

API = "https://openapi.sosovalue.com/openapi/v1"
PARAMS = {"symbol": "BTC", "country_code": "US"}
KEY_ENV = "SOSOVALUE_API_KEY"
ENV_PATH = config.ROOT / ".env"
KEY_URL = "https://sosovalue.com/developer/dashboard"
SOURCE_URL = "https://sosovalue.com/assets/etf/us-btc-spot"
TIMEOUT = 15.0
TTL = 1800            # flows settle once a day; one refresh is 2 + one call per fund (limit: 20 a minute)
RETRY_AFTER = 120     # after a failure, wait this long before asking again
MAX_FUNDS = 17        # stay under the 20-a-minute limit in one refresh
HISTORY_DAYS = 30
FUND_FIELDS = ("fee", "price", "prem_dsc", "net_inflow", "cum_inflow", "net_assets", "value_traded")


class EtfError(Exception):
    """The ETF data could not be read; the message is short and shown on the page."""


def read_dotenv(path: Path) -> dict[str, str]:
    """NAME=value lines from a .env file; blank lines, # comments and an "export " prefix are allowed,
    and quotes around the value are dropped. A missing file gives {}."""
    out = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.removeprefix("export ").split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[name.strip()] = value.strip()
    return out


def read_key(path: Path = ENV_PATH) -> str | None:
    """The SoSoValue API key: the environment variable first, else the .env file. None when there is none."""
    key = os.environ.get(KEY_ENV, "").strip() or read_dotenv(path).get(KEY_ENV, "")
    return key or None


def unwrap(payload):
    """SoSoValue answers {"code": 0, "message": ..., "data": ...}; errors carry a non-zero code."""
    if isinstance(payload, dict) and "code" in payload:
        if payload.get("code") not in (0, "0"):
            raise EtfError(f"SoSoValue said: {payload.get('message') or payload.get('code')}")
        return payload.get("data")
    return payload


def num(v) -> float | None:
    """A number from SoSoValue (sometimes a string); None when missing or not a number."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def day(v) -> str | None:
    """A date as yyyy-mm-dd, from either "2024-04-12" or a UTC millisecond timestamp."""
    if v is None or v == "":
        return None
    if isinstance(v, str) and not v.isdigit():
        return v[:10]
    try:
        return datetime.fromtimestamp(int(v) / 1000, timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def parse_fund(meta: dict, snap: dict | None) -> dict:
    """One table row. Ratios stay ratios (fee 0.0025 = 0.25 %); the page formats them."""
    snap = snap or {}
    return {
        "ticker": str(meta["ticker"]), "name": str(meta.get("name") or meta["ticker"]),
        "exchange": meta.get("exchange") or "", "date": day(snap.get("date")),
        "fee": num(snap.get("sponsor_fee")), "price": num(snap.get("mkt_price")),
        "prem_dsc": num(snap.get("prem_dsc")), "net_inflow": num(snap.get("net_inflow")),
        "cum_inflow": num(snap.get("cum_inflow")), "net_assets": num(snap.get("net_assets")),
        "value_traded": num(snap.get("value_traded")),
    }


def parse_summary(rows) -> tuple[dict | None, list]:
    """Daily totals (newest first) -> (the newest day's totals, [[date, net inflow], ...] oldest first)."""
    if not isinstance(rows, list):
        raise EtfError("SoSoValue's totals have changed")
    days = []
    for r in rows:
        if isinstance(r, dict) and day(r.get("date")) and num(r.get("total_net_inflow")) is not None:
            days.append({"date": day(r["date"]), "net_inflow": num(r["total_net_inflow"]),
                         "value_traded": num(r.get("total_value_traded")),
                         "net_assets": num(r.get("total_net_assets")), "cum_inflow": num(r.get("cum_net_inflow"))})
    days.sort(key=lambda d: d["date"])
    return (days[-1] if days else None), [[d["date"], d["net_inflow"]] for d in days[-HISTORY_DAYS:]]


def fetch(key: str, client: httpx.Client | None = None) -> dict:
    """The whole table: the fund list, each fund's latest figures and the daily totals."""
    own = client is None
    client = client or httpx.Client(base_url=API, timeout=TIMEOUT, headers={"x-soso-api-key": key})

    def get(path: str, **params):
        try:
            r = client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise EtfError(f"Couldn't reach SoSoValue ({type(exc).__name__})") from exc
        if r.status_code in (401, 403):
            raise EtfError(f"SoSoValue refused the API key (HTTP {r.status_code}); check {KEY_ENV} in .env")
        if r.status_code == 429:
            raise EtfError("SoSoValue's limit of 20 requests a minute was reached; try again in a minute")
        try:
            payload = r.json()
        except ValueError as exc:
            raise EtfError(f"SoSoValue answered HTTP {r.status_code} without data") from exc
        if r.status_code >= 400 and not (isinstance(payload, dict) and "code" in payload):
            raise EtfError(f"SoSoValue answered HTTP {r.status_code}")
        return unwrap(payload)

    try:
        funds = get("/etfs", **PARAMS)
        if not isinstance(funds, list) or not all(isinstance(f, dict) and f.get("ticker") for f in funds):
            raise EtfError("SoSoValue's fund list has changed")
        totals, history = parse_summary(get("/etfs/summary-history", **PARAMS, limit=HISTORY_DAYS))
        rows, missing = [], []
        for f in funds[:MAX_FUNDS]:
            try:
                snap = get(f"/etfs/{f['ticker']}/market-snapshot")
                rows.append(parse_fund(f, snap if isinstance(snap, dict) else None))
            except EtfError:
                rows.append(parse_fund(f, None))
                missing.append(str(f["ticker"]))
    finally:
        if own:
            client.close()
    rows.sort(key=lambda r: r["net_assets"] if r["net_assets"] is not None else -1, reverse=True)
    return {"funds": rows, "totals": totals, "history": history, "missing": missing}


class BtcEtf:
    """Reuses the last answer for TTL seconds, keeps showing it if a later fetch fails, and waits
    RETRY_AFTER seconds after a failure so page opens can't run through SoSoValue's rate limit."""

    def __init__(self, get: Callable[[str], dict] = fetch, key: Callable[[], str | None] = read_key,
                 clock: Callable[[], float] = time.time):
        self._get, self._key, self._clock = get, key, clock
        self._hit: tuple[float, dict] | None = None
        self._fail: tuple[float, str] | None = None
        self._lock = threading.Lock()

    def snapshot(self) -> dict:
        base = {"funds": [], "totals": None, "history": [], "missing": [], "error": None, "needs_key": False,
                "key_env": KEY_ENV, "env_file": str(ENV_PATH), "key_url": KEY_URL, "source_url": SOURCE_URL}
        key = self._key()
        if not key:
            return {**base, "needs_key": True}
        with self._lock:
            now = self._clock()
            hit, fail = self._hit, self._fail
            fresh = hit is not None and now - hit[0] < TTL
            waiting = fail is not None and now - fail[0] < RETRY_AFTER
            if not fresh and not waiting:
                try:
                    data = self._get(key)
                    self._hit = hit = (self._clock(), data)
                    self._fail = fail = None
                except EtfError as exc:
                    self._fail = fail = (self._clock(), str(exc))
        if hit is None:
            return {**base, "error": fail[1] if fail else "No data yet"}
        return {**base, **hit[1], "as_of": datetime.fromtimestamp(hit[0], timezone.utc).isoformat()}
