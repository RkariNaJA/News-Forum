"""Telegram price messages: BTC, ETH, ADA, OP and gold sent to the user's bot at fixed times of day.

The bot token and chat id come from TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (environment first, else the
project's git-ignored .env). With either missing, nothing is sent. The token is never logged.
"""
from __future__ import annotations

import html
import math
import os
import re
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
SEND_TIMEOUT = 40.0   # Telegram may hold a request ~33 s before answering 429; wait long enough to see it

BINANCE_URL = "https://api.binance.com/api/v3/ticker/24hr"
YAHOO_GOLD_URL = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"   # gold futures, per troy ounce
COINS = (("BTC", "BTCUSDT"), ("ETH", "ETHUSDT"), ("ADA", "ADAUSDT"), ("OP", "OPUSDT"))
GOLD_FALLBACK = "PAXGUSDT"   # a Binance token backed by gold; used when Yahoo fails
SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"

SLOTS = ("08:30", "10:30", "12:30", "14:30", "16:30", "17:30")   # this PC's local time, every day
GRACE_MINUTES = 10   # a slot seen later than this (PC asleep or off) is skipped, never sent late
POLL_SECONDS = 30
NOT_SET_UP = f"Not set up: add {TOKEN_ENV} and {CHAT_ENV} to .env"
TOKEN_RE = re.compile(r"[0-9]+:[A-Za-z0-9_-]+")   # BotFather's shape: bot id, colon, letters/digits/_/-
BAD_TOKEN = f"{TOKEN_ENV} in .env looks wrong: it should look like 123456789:AAH-xyz (no spaces or quotes)"
SLOT_KEY_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}")


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


def _reason(exc: Exception) -> str:
    if not isinstance(exc, httpx.HTTPError):
        return f"Unexpected reply ({type(exc).__name__})"
    return describe_error(exc).replace("Feed moved or removed", "Not found")   # feeds' wording, for a price


def _failure(name: str, exc: Exception) -> dict:
    return {"name": name, "error": _reason(exc)}


_BAD_REPLY = (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError)


def get_quotes(client: httpx.Client) -> list[dict]:
    """The COINS, then GOLD. A price that can't be read becomes {"name", "error"}; PAXG gold carries "why"."""
    out = []
    for name, symbol in COINS:
        try:
            out.append(_binance(name, symbol, client))
        except _BAD_REPLY as exc:
            out.append(_failure(name, exc))
    try:
        out.append(_yahoo_gold(client))
    except _BAD_REPLY as yahoo_exc:
        try:
            out.append({**_binance("GOLD", GOLD_FALLBACK, client), "note": "PAXG", "why": _reason(yahoo_exc)})
        except _BAD_REPLY as exc:
            out.append(_failure("GOLD", exc))
    return out


# ---- message --------------------------------------------------------------------------------------
def _line(q: dict) -> str:
    if "error" in q:
        return f"{q['name']:<4}   unavailable"
    d = 4 if q["price"] < 1 else 2   # ADA, OP trade under $1: 2 decimals would hide the change
    return (f"{q['name']:<4} {'$' + format(q['price'], f',.{d}f'):>11} {format(q['change'], f'+,.{d}f'):>9}"
            f"  ({q['pct']:+.2f}%)")


def format_message(quotes: list[dict], now: datetime) -> str:
    """Telegram HTML: a header, the prices in a monospace block (so columns line up), and a source note."""
    rows = html.escape("\n".join(_line(q) for q in quotes), quote=False)
    paxg = any(q.get("note") == "PAXG" for q in quotes)
    gold = "24h change (Binance PAXG)" if paxg else "since previous close (Yahoo gold futures)"
    return (f"📊 Prices · {now:%a %d %b %H:%M}\n<pre>{rows}</pre>\n"
            f"Crypto: 24h change (Binance) · Gold: {gold}")


# ---- sending --------------------------------------------------------------------------------------
def send(token: str, chat_id: str, text: str, client: httpx.Client) -> None:
    """Post one HTML message. Raises TelegramError; the token (part of the URL) is scrubbed from it."""
    if not TOKEN_RE.fullmatch(token):   # it goes into the URL: a stray character could crash or misdirect
        raise TelegramError(BAD_TOKEN)
    try:
        r = client.post(SEND_URL.format(token=token), timeout=SEND_TIMEOUT,
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


def _gaps(quotes: list[dict]) -> str:
    """For the log: which prices were missing and why, and whether gold came from PAXG."""
    notes = [f"{q['name']} unavailable: {q['error']}" for q in quotes if "error" in q]
    notes += [f"gold from PAXG, Yahoo failed: {q['why']}" for q in quotes if q.get("note") == "PAXG"]
    return f" ({'; '.join(notes)})" if notes else ""


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
        quotes = get_quotes(client)
        send(token, chat, format_message(quotes, now or datetime.now()), client)
        return "Sent" + _gaps(quotes)
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
    """Background loop: checks the clock every POLL_SECONDS and sends the prices at each slot, once.

    With state_path, the last slot sent is kept in that file, so a restart inside a slot's window
    doesn't send it again. A missing, unreadable or garbled file just means "nothing sent yet".
    """

    def __init__(self, send: Callable[[], str] = send_prices, clock: Callable[[], datetime] = datetime.now,
                 poll_seconds: float = POLL_SECONDS, state_path: Path | None = None):
        self._send, self._clock, self._poll, self._state = send, clock, poll_seconds, state_path
        self._sent: set[str] = set()
        last = self._load_last()
        if last:
            self._sent.add(last)
        self._said_not_set_up = False

    def _load_last(self) -> str | None:
        if self._state is None:
            return None
        try:
            text = self._state.read_text(encoding="utf-8").strip()
        except (OSError, ValueError):
            return None
        return text if SLOT_KEY_RE.fullmatch(text) else None

    def _save_last(self, key: str) -> None:
        if self._state is None:
            return
        tmp = self._state.with_name(self._state.name + ".tmp")
        try:
            tmp.write_text(key + "\n", encoding="utf-8")
            os.replace(tmp, self._state)
        except OSError:   # can't record it: the send still happens, only restart protection is lost
            pass

    def tick(self) -> None:
        key = due_slot(self._clock(), self._sent)
        if key is None:
            return
        self._sent.add(key)   # before sending: a failure is not retried every poll
        self._save_last(key)
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
