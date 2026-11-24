import json
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
    "ADAUSDT": {"lastPrice": "0.14890000", "priceChange": "0.00300000", "priceChangePercent": "2.056"},
    "OPUSDT": {"lastPrice": "0.07170000", "priceChange": "0.00010000", "priceChangePercent": "0.140"},
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
        quotes = get_quotes(c)
    assert [q["name"] for q in quotes] == ["BTC", "ETH", "ADA", "OP", "GOLD"]
    btc, eth, ada, op, gold = quotes
    assert btc == {"name": "BTC", "price": 60453.40, "change": -853.79, "pct": -1.393, "note": None}
    assert eth["price"] == 3012.10
    assert ada == {"name": "ADA", "price": 0.1489, "change": 0.003, "pct": 2.056, "note": None}
    assert op == {"name": "OP", "price": 0.0717, "change": 0.0001, "pct": 0.14, "note": None}
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
        gold = get_quotes(c)[-1]
    assert gold == {"name": "GOLD", "price": 3623.25, "change": 27.11, "pct": 0.754, "note": "PAXG"}


def _yahoo_meta(price, prev):
    # json.dumps writes NaN / Infinity as a real server might (httpx's json= refuses them)
    body = json.dumps({"chart": {"result": [{"meta": {"regularMarketPrice": price, "chartPreviousClose": prev}}]}})
    return lambda req: httpx.Response(200, content=body.encode(), headers={"content-type": "application/json"})


@pytest.mark.parametrize("price, prev", [
    (3629.3, 0), (float("nan"), 3651.4), (3629.3, float("inf")), (-1.0, 3651.4), (0, 3651.4),
])
def test_bad_yahoo_numbers_fall_back_to_paxg(price, prev):
    with _client(yahoo=_yahoo_meta(price, prev)) as c:
        gold = get_quotes(c)[-1]
    assert gold["note"] == "PAXG" and gold["price"] == 3623.25


@pytest.mark.parametrize("field, value", [("lastPrice", "nan"), ("lastPrice", "0"), ("priceChange", "inf")])
def test_bad_binance_numbers_make_that_price_unavailable(monkeypatch, field, value):
    monkeypatch.setitem(BINANCE, "BTCUSDT", {**BINANCE["BTCUSDT"], field: value})
    with _client() as c:
        btc, eth = get_quotes(c)[:2]
    assert btc["name"] == "BTC" and btc["error"] and eth["price"] == 3012.10


def test_one_failed_price_keeps_the_others():
    with _client(binance_down=("ETHUSDT",)) as c:
        btc, eth, ada, op, gold = get_quotes(c)
    assert btc["price"] == 60453.40 and ada["price"] == 0.1489 and gold["price"] == 3629.3
    assert eth["name"] == "ETH" and eth["error"] and "price" not in eth


def test_gold_unavailable_when_both_sources_fail():
    with _client(yahoo=lambda req: httpx.Response(503), binance_down=("PAXGUSDT",)) as c:
        gold = get_quotes(c)[-1]
    assert gold["name"] == "GOLD" and gold["error"]


# ---- message --------------------------------------------------------------------------------------
QUOTES = [
    {"name": "BTC", "price": 60453.40, "change": -853.79, "pct": -1.393, "note": None},
    {"name": "ETH", "price": 3012.10, "change": -40.22, "pct": -1.318, "note": None},
    {"name": "ADA", "price": 0.1489, "change": 0.003, "pct": 2.056, "note": None},
    {"name": "OP", "price": 0.0717, "change": 0.0001, "pct": 0.14, "note": None},
    {"name": "GOLD", "price": 3629.3, "change": -22.1, "pct": -0.6052, "note": None},
]


def test_message_format():
    assert format_message(QUOTES, NOW) == (
        "📊 Prices · Tue 24 Nov 10:30\n"
        "<pre>BTC   $60,453.40   -853.79  (-1.39%)\n"
        "ETH    $3,012.10    -40.22  (-1.32%)\n"
        "ADA      $0.1489   +0.0030  (+2.06%)\n"
        "OP       $0.0717   +0.0001  (+0.14%)\n"
        "GOLD   $3,629.30    -22.10  (-0.61%)</pre>\n"
        "Crypto: 24h change (Binance) · Gold: since previous close (Yahoo gold futures)")


@pytest.mark.parametrize("price, change, line", [
    (1.0, 0.02, "ADA        $1.00     +0.02  (+2.00%)"),        # $1 and up: 2 decimals
    (0.9999, -0.0004, "ADA      $0.9999   -0.0004  (+2.00%)"),  # under $1: 4 decimals
])
def test_prices_under_one_dollar_get_four_decimals(price, change, line):
    quote = {"name": "ADA", "price": price, "change": change, "pct": 2.0, "note": None}
    assert format_message([quote], NOW).splitlines()[1] == "<pre>" + line + "</pre>"


def test_message_marks_rises_unavailable_and_paxg():
    quotes = [{"name": "BTC", "price": 101234.5, "change": 1500.0, "pct": 1.5, "note": None},
              {"name": "ETH", "error": "Timed out"},
              {"name": "GOLD", "price": 3623.25, "change": 27.11, "pct": 0.754, "note": "PAXG"}]
    lines = format_message(quotes, NOW).splitlines()
    assert lines[1] == "<pre>BTC  $101,234.50 +1,500.00  (+1.50%)"
    assert lines[2] == "ETH    unavailable"
    assert lines[3] == "GOLD   $3,623.25    +27.11  (+0.75%)</pre>"
    assert lines[4] == "Crypto: 24h change (Binance) · Gold: 24h change (Binance PAXG)"


# ---- sending --------------------------------------------------------------------------------------
TOKEN = "123456:SECRET-token"


def _tg_client(reply):
    seen = []
    def handler(req):
        seen.append(req)
        if req.url.host == "api.telegram.org":
            return reply(req)
        return _price_reply(req)
    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def _price_reply(req):
    if req.url.host == "query1.finance.yahoo.com":
        return httpx.Response(200, json=YAHOO_OK)
    return httpx.Response(200, json=BINANCE[req.url.params["symbol"]])


def test_send_posts_html_message_to_the_chat():
    client, seen = _tg_client(lambda req: httpx.Response(200, json={"ok": True, "result": {}}))
    with client:
        telegram.send(TOKEN, "555", "<pre>hi</pre>", client)
    req = seen[0]
    assert req.method == "POST" and req.url.path == f"/bot{TOKEN}/sendMessage"
    assert json.loads(req.content) == {"chat_id": "555", "text": "<pre>hi</pre>", "parse_mode": "HTML"}


def test_send_error_hides_token():
    def down(req):
        raise httpx.ConnectError(f"connection failed for {req.url}")
    client, _ = _tg_client(down)
    with client, pytest.raises(telegram.TelegramError) as info:
        telegram.send(TOKEN, "555", "x", client)
    assert TOKEN not in str(info.value) and "SECRET" not in str(info.value)
    assert "Couldn't connect" in str(info.value)


def test_telegram_refusal_is_readable():
    client, _ = _tg_client(lambda req: httpx.Response(
        400, json={"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}))
    with client, pytest.raises(telegram.TelegramError, match="Telegram refused the message: Bad Request: chat not found"):
        telegram.send(TOKEN, "555", "x", client)


def test_send_prices_not_set_up(tmp_path):
    client, seen = _tg_client(lambda req: httpx.Response(200, json={"ok": True}))
    with client:
        status = telegram.send_prices(tmp_path / ".env", client, NOW)
    assert status == "Not set up: add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env"
    assert seen == []


def test_send_prices_sends_the_formatted_message(tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_CHAT_ID=555\n", encoding="utf-8")
    client, seen = _tg_client(lambda req: httpx.Response(200, json={"ok": True}))
    with client:
        assert telegram.send_prices(env, client, NOW) == "Sent"
    sent = json.loads([r for r in seen if r.url.host == "api.telegram.org"][0].content)
    assert sent["text"].startswith("📊 Prices · Tue 24 Nov 10:30\n<pre>BTC   $60,453.40")


def test_send_prices_failure_is_a_status_without_the_token(tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_CHAT_ID=555\n", encoding="utf-8")
    def down(req):
        raise httpx.ConnectError(f"connection failed for {req.url}")
    client, _ = _tg_client(down)
    with client:
        status = telegram.send_prices(env, client, NOW)
    assert status.startswith("Failed:") and "SECRET" not in status


# ---- schedule -------------------------------------------------------------------------------------
def test_slots_are_the_agreed_times():
    assert telegram.SLOTS == ("08:30", "10:30", "12:30", "14:30", "16:30", "17:30")


@pytest.mark.parametrize("hm, due", [
    ((8, 30), "2026-11-24 08:30"), ((8, 35), "2026-11-24 08:30"), ((8, 39), "2026-11-24 08:30"),
    ((8, 40), None), ((8, 41), None), ((8, 29), None), ((17, 30), "2026-11-24 17:30"),
    ((18, 0), None), ((18, 30), None), ((0, 0), None),
])
def test_due_slot_window(hm, due):
    assert telegram.due_slot(datetime(2026, 11, 24, *hm, 15), set()) == due


def test_due_slot_never_repeats_a_sent_slot():
    assert telegram.due_slot(datetime(2026, 11, 24, 8, 31), {"2026-11-24 08:30"}) is None
    assert telegram.due_slot(datetime(2026, 11, 25, 8, 31), {"2026-11-24 08:30"}) == "2026-11-25 08:30"


def test_notifier_sends_each_slot_once_and_survives_errors(capsys):
    calls = []
    def flaky_send():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return "Sent"
    clock = iter([datetime(2026, 11, 24, 8, 30), datetime(2026, 11, 24, 8, 31),   # 08:30 fails once
                  datetime(2026, 11, 24, 9, 0),                                    # nothing due
                  datetime(2026, 11, 24, 10, 30), datetime(2026, 11, 24, 10, 32)])  # 10:30 sent once
    n = telegram.PriceNotifier(send=flaky_send, clock=lambda: next(clock))
    for _ in range(5):
        n.tick()
    assert len(calls) == 2
    out = capsys.readouterr().out
    assert "08:30" in out and "RuntimeError" in out and "10:30: Sent" in out


def test_notifier_says_not_set_up_only_once(capsys):
    clock = iter([datetime(2026, 11, 24, 8, 30), datetime(2026, 11, 24, 10, 30)])
    n = telegram.PriceNotifier(send=lambda: "Not set up: add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env",
                               clock=lambda: next(clock))
    n.tick(); n.tick()
    assert capsys.readouterr().out.count("Not set up") == 1


class _StopLoop(BaseException):
    pass


def test_loop_keeps_running_after_an_error_outside_send(monkeypatch):
    # e.g. the log file failing to write: the timer must not die silently for the rest of the session
    naps = []
    def nap(seconds):
        naps.append(seconds)
        if len(naps) == 3:
            raise _StopLoop
    monkeypatch.setattr(telegram.time, "sleep", nap)
    calls = []
    def clock():
        calls.append(1)
        if len(calls) == 1:
            raise OSError("log file unavailable")
        return datetime(2026, 11, 24, 9, 0)
    n = telegram.PriceNotifier(send=lambda: "Sent", clock=clock, poll_seconds=30)
    with pytest.raises(_StopLoop):
        n._run()
    assert len(calls) == 3 and naps == [30, 30, 30]
