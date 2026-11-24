from datetime import datetime

import httpx
import pytest

from news import telegram
from news.telegram import format_message, get_quotes, read_settings

NOW = datetime(2026, 11, 24, 10, 30)


@pytest.fixture(autouse=True)
def no_env_vars(monkeypatch):
    monkeypatch.delenv(telegram.TOKEN_ENV, raising=False)
    monkeypatch.delenv(telegram.CHAT_ENV, raising=False)


# ---- settings -------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "",
    "TELEGRAM_BOT_TOKEN=123:abc\nTELEGRAM_CHAT_ID=\n",
    "TELEGRAM_BOT_TOKEN=\nTELEGRAM_CHAT_ID=555\n",
    "TELEGRAM_BOT_TOKEN=   \nTELEGRAM_CHAT_ID=  \n",
])
def test_settings_need_both_values(tmp_path, text):
    env = tmp_path / ".env"
    env.write_text(text, encoding="utf-8")
    assert read_settings(env) is None


def test_settings_from_env_file_and_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SOSOVALUE_API_KEY=x\nTELEGRAM_BOT_TOKEN=123:abc\nTELEGRAM_CHAT_ID=555\n", encoding="utf-8")
    assert read_settings(env) == ("123:abc", "555")
    monkeypatch.setenv(telegram.CHAT_ENV, "777")      # the environment wins over .env
    assert read_settings(env) == ("123:abc", "777")
    assert read_settings(tmp_path / "missing.env") is None   # no token anywhere; a missing file never raises


# ---- prices ---------------------------------------------------------------------------------------
BINANCE = {
    "BTCUSDT": {"lastPrice": "60453.40", "priceChange": "-853.79", "priceChangePercent": "-1.393"},
    "ETHUSDT": {"lastPrice": "3012.10", "priceChange": "-40.22", "priceChangePercent": "-1.318"},
    "PAXGUSDT": {"lastPrice": "3623.25", "priceChange": "27.11", "priceChangePercent": "0.754"},
}
YAHOO_OK = {"chart": {"result": [{"meta": {"regularMarketPrice": 3629.3, "chartPreviousClose": 3651.4}}]}}


def _client(yahoo=lambda req: httpx.Response(200, json=YAHOO_OK), binance_down=()):
    def handler(req):
        if req.url.host == "query1.finance.yahoo.com":
            assert "GC=F" in req.url.path
            return yahoo(req)
        symbol = req.url.params["symbol"]
        if symbol in binance_down:
            raise httpx.ConnectError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF")
        return httpx.Response(200, json=BINANCE[symbol])
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_quotes_from_binance_and_yahoo():
    with _client() as c:
        btc, eth, gold = get_quotes(c)
    assert btc == {"name": "BTC", "price": 60453.40, "change": -853.79, "pct": -1.393, "note": None}
    assert eth["name"] == "ETH" and eth["price"] == 3012.10
    assert gold["name"] == "GOLD" and gold["price"] == 3629.3 and gold["note"] is None
    assert gold["change"] == pytest.approx(-22.1)
    assert gold["pct"] == pytest.approx(-22.1 / 3651.4 * 100)


@pytest.mark.parametrize("yahoo", [
    lambda req: httpx.Response(500),
    lambda req: httpx.Response(200, json={"chart": {"result": [{"meta": {"regularMarketPrice": None,
                                                                         "chartPreviousClose": 3651.4}}]}}),
    lambda req: httpx.Response(200, json={"chart": {"result": None, "error": {"code": "Not Found"}}}),
    lambda req: httpx.Response(200, text="<html>not json</html>"),
])
def test_gold_falls_back_to_paxg(yahoo):
    with _client(yahoo=yahoo) as c:
        gold = get_quotes(c)[2]
    assert gold == {"name": "GOLD", "price": 3623.25, "change": 27.11, "pct": 0.754, "note": "PAXG"}


def test_one_failed_price_keeps_the_others():
    with _client(binance_down=("ETHUSDT",)) as c:
        btc, eth, gold = get_quotes(c)
    assert btc["price"] == 60453.40 and gold["price"] == 3629.3
    assert eth["name"] == "ETH" and eth["error"] and "price" not in eth


def test_gold_unavailable_when_both_sources_fail():
    with _client(yahoo=lambda req: httpx.Response(503), binance_down=("PAXGUSDT",)) as c:
        gold = get_quotes(c)[2]
    assert gold["name"] == "GOLD" and gold["error"]


# ---- message --------------------------------------------------------------------------------------
QUOTES = [
    {"name": "BTC", "price": 60453.40, "change": -853.79, "pct": -1.393, "note": None},
    {"name": "ETH", "price": 3012.10, "change": -40.22, "pct": -1.318, "note": None},
    {"name": "GOLD", "price": 3629.3, "change": -22.1, "pct": -0.6052, "note": None},
]


def test_message_format():
    assert format_message(QUOTES, NOW) == (
        "📊 Prices · Tue 24 Nov 10:30\n"
        "<pre>BTC   $60,453.40   -853.79  (-1.39%)\n"
        "ETH    $3,012.10    -40.22  (-1.32%)\n"
        "GOLD   $3,629.30    -22.10  (-0.61%)</pre>\n"
        "BTC/ETH: 24h change (Binance) · Gold: since previous close (Yahoo gold futures)")


def test_message_marks_rises_unavailable_and_paxg():
    quotes = [{"name": "BTC", "price": 101234.5, "change": 1500.0, "pct": 1.5, "note": None},
              {"name": "ETH", "error": "Timed out"},
              {"name": "GOLD", "price": 3623.25, "change": 27.11, "pct": 0.754, "note": "PAXG"}]
    lines = format_message(quotes, NOW).splitlines()
    assert lines[1] == "<pre>BTC  $101,234.50 +1,500.00  (+1.50%)"
    assert lines[2] == "ETH    unavailable"
    assert lines[3] == "GOLD   $3,623.25    +27.11  (+0.75%)</pre>"
    assert lines[4] == "BTC/ETH: 24h change (Binance) · Gold: 24h change (Binance PAXG)"
