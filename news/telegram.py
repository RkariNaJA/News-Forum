"""Telegram price messages: BTC, ETH and gold sent to the user's bot at fixed times of day.

The bot token and chat id come from TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (environment first, else the
project's git-ignored .env). With either missing, nothing is sent. The token is never logged.
"""
from __future__ import annotations

import html
import math
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import httpx

from .etf import ENV_PATH, read_dotenv
from .feeds import USER_AGENT, describe_error

TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
CHAT_ENV = "TELEGRAM_CHAT_ID"
TIMEOUT = 15.0

BINANCE_URL = "https://api.binance.com/api/v3/ticker/24hr"
YAHOO_GOLD_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"   # gold futures, per troy ounce
COINS = (("BTC", "BTCUSDT"), ("ETH", "ETHUSDT"))
GOLD_FALLBACK = "PAXGUSDT"   # a Binance token backed by gold; used when Yahoo fails
SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"

SLOTS = ("08:30", "10:30", "12:30", "14:30", "16:30", "17:30")   # this PC's local time, every day
GRACE_MINUTES = 10   # a slot seen later than this (PC asleep or off) is skipped, never sent late
POLL_SECONDS = 30
NOT_SET_UP = f"Not set up: add {TOKEN_ENV} and {CHAT_ENV} to .env"


class TelegramError(Exception):
    """The message wasn't sent. The text is short and never contains the bot token."""


# ---- settings -------------------------------------------------------------------------------------
def read_settings(path: Path = ENV_PATH) -> tuple[str, str] | None:
    """(bot token, chat id), each from the environment first, else the .env file. None unless both are set."""
    file = read_dotenv(path)
    token = os.environ.get(TOKEN_ENV, "").strip() or file.get(TOKEN_ENV, "").strip()
    chat = os.environ.get(CHAT_ENV, "").strip() or file.get(CHAT_ENV, "").strip()
    return (token, chat) if token and chat else None


# ---- prices ---------------------------------------------------------------------------------------
def _num(value, positive: bool = False) -> float:
    """A finite number from a price API (a price must also be > 0); anything else raises ValueError."""
    x = float(value)
    if not math.isfinite(x) or (positive and x <= 0):
        raise ValueError(f"bad number {value!r}")
    return x


def _binance(name: str, symbol: str, client: httpx.Client) -> dict:
    r = client.get(BINANCE_URL, params={"symbol": symbol})
    r.raise_for_status()
    j = r.json()
    return {"name": name, "price": _num(j["lastPrice"], positive=True), "change": _num(j["priceChange"]),
            "pct": _num(j["priceChangePercent"]), "note": None}


def _yahoo_gold(client: httpx.Client) -> dict:
    r = client.get(YAHOO_GOLD_URL, params={"range": "1d", "interval": "1d"})
    r.raise_for_status()
    meta = r.json()["chart"]["result"][0]["meta"]
    price, prev = _num(meta["regularMarketPrice"], positive=True), _num(meta["chartPreviousClose"], positive=True)
    return {"name": "GOLD", "price": price, "change": price - prev, "pct": (price - prev) / prev * 100,
            "note": None}


def _failure(name: str, exc: Exception) -> dict:
    msg = describe_error(exc) if isinstance(exc, httpx.HTTPError) else f"Unexpected reply ({type(exc).__name__})"
    return {"name": name, "error": msg}


_BAD_REPLY = (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError)


def get_quotes(client: httpx.Client) -> list[dict]:
    """BTC, ETH and GOLD, in that order. A price that can't be read becomes {"name", "error"}."""
    out = []
    for name, symbol in COINS:
        try:
            out.append(_binance(name, symbol, client))
        except _BAD_REPLY as exc:
            out.append(_failure(name, exc))
    try:
        out.append(_yahoo_gold(client))
    except _BAD_REPLY:
        try:
            out.append({**_binance("GOLD", GOLD_FALLBACK, client), "note": "PAXG"})
        except _BAD_REPLY as exc:
            out.append(_failure("GOLD", exc))
    return out


# ---- message --------------------------------------------------------------------------------------
def _line(q: dict) -> str:
    if "error" in q:
        return f"{q['name']:<4}   unavailable"
    return f"{q['name']:<4} {'$' + format(q['price'], ',.2f'):>11} {q['change']:>+9,.2f}  ({q['pct']:+.2f}%)"


def format_message(quotes: list[dict], now: datetime) -> str:
    """Telegram HTML: a header, the prices in a monospace block (so columns line up), and a source note."""
    rows = html.escape("\n".join(_line(q) for q in quotes), quote=False)
    paxg = any(q.get("note") == "PAXG" for q in quotes)
    gold = "24h change (Binance PAXG)" if paxg else "since previous close (Yahoo gold futures)"
    return (f"📊 Prices · {now:%a %d %b %H:%M}\n<pre>{rows}</pre>\n"
            f"BTC/ETH: 24h change (Binance) · Gold: {gold}")


# ---- sending --------------------------------------------------------------------------------------
def send(token: str, chat_id: str, text: str, client: httpx.Client) -> None:
    """Post one HTML message. Raises TelegramError; the token (part of the URL) is scrubbed from it."""
    try:
        r = client.post(SEND_URL.format(token=token),
                        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    except httpx.HTTPError as exc:
        raise TelegramError(f"Couldn't reach Telegram: {describe_error(exc)}".replace(token, "***")) from None
    try:
        reply = r.json()
    except ValueError:
        reply = {}
    if r.status_code != 200 or not reply.get("ok"):
        why = reply.get("description") or f"HTTP {r.status_code}"
        raise TelegramError(f"Telegram refused the message: {why}".replace(token, "***"))


def send_prices(path: Path = ENV_PATH, client: httpx.Client | None = None,
                now: datetime | None = None) -> str:
    """Fetch the prices and send them. Returns a one-line status ("Sent", not set up, or why it failed)."""
    settings = read_settings(path)
    if settings is None:
        return NOT_SET_UP
    token, chat = settings
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    try:
        send(token, chat, format_message(get_quotes(client), now or datetime.now()), client)
        return "Sent"
    except TelegramError as exc:
        return f"Failed: {exc}"
    finally:
        if own:
            client.close()


# ---- schedule -------------------------------------------------------------------------------------
def due_slot(now: datetime, sent: set[str]) -> str | None:
    """The slot to send now ("2026-11-24 08:30"), if one started less than GRACE_MINUTES ago and isn't sent."""
    for slot in SLOTS:
        h, m = map(int, slot.split(":"))
        start = now.replace(hour=h, minute=m, second=0, microsecond=0)
        key = f"{now:%Y-%m-%d} {slot}"
        if start <= now < start + timedelta(minutes=GRACE_MINUTES) and key not in sent:
            return key
    return None


class PriceNotifier:
    """Background loop: checks the clock every POLL_SECONDS and sends the prices at each slot, once."""

    def __init__(self, send: Callable[[], str] = send_prices, clock: Callable[[], datetime] = datetime.now,
                 poll_seconds: float = POLL_SECONDS):
        self._send, self._clock, self._poll = send, clock, poll_seconds
        self._sent: set[str] = set()
        self._said_not_set_up = False

    def tick(self) -> None:
        key = due_slot(self._clock(), self._sent)
        if key is None:
            return
        self._sent.add(key)   # before sending: a failure is not retried every poll
        try:
            status = self._send()
        except Exception as exc:  # a bug here must not stop later slots
            status = f"Failed ({type(exc).__name__})"
        if status == NOT_SET_UP:
            if self._said_not_set_up:
                return
            self._said_not_set_up = True
        print(f"Telegram prices {key}: {status}", flush=True)

    def _run(self) -> None:
        while True:
            try:
                self.tick()
            except Exception:  # e.g. the log file can't be written: keep the timer alive for later slots
                pass
            time.sleep(self._poll)

    def start(self) -> None:
        print(f"Telegram prices: daily at {', '.join(SLOTS)}", flush=True)
        threading.Thread(target=self._run, name="telegram-prices", daemon=True).start()
