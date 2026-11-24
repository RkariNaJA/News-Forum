"""Telegram price messages: BTC, ETH and gold sent to the user's bot at fixed times of day.

The bot token and chat id come from TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (environment first, else the
project's git-ignored .env). With either missing, nothing is sent. The token is never logged.
"""
from __future__ import annotations

import html
import os
from datetime import datetime
from pathlib import Path

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


# ---- settings -------------------------------------------------------------------------------------
def read_settings(path: Path = ENV_PATH) -> tuple[str, str] | None:
    """(bot token, chat id), each from the environment first, else the .env file. None unless both are set."""
    file = read_dotenv(path)
    token = os.environ.get(TOKEN_ENV, "").strip() or file.get(TOKEN_ENV, "").strip()
    chat = os.environ.get(CHAT_ENV, "").strip() or file.get(CHAT_ENV, "").strip()
    return (token, chat) if token and chat else None


# ---- prices ---------------------------------------------------------------------------------------
def _binance(name: str, symbol: str, client: httpx.Client) -> dict:
    r = client.get(BINANCE_URL, params={"symbol": symbol})
    r.raise_for_status()
    j = r.json()
    return {"name": name, "price": float(j["lastPrice"]), "change": float(j["priceChange"]),
            "pct": float(j["priceChangePercent"]), "note": None}


def _yahoo_gold(client: httpx.Client) -> dict:
    r = client.get(YAHOO_GOLD_URL, params={"range": "1d", "interval": "1d"})
    r.raise_for_status()
    meta = r.json()["chart"]["result"][0]["meta"]
    price, prev = float(meta["regularMarketPrice"]), float(meta["chartPreviousClose"])
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
