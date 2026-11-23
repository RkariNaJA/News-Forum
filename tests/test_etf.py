import httpx
import pytest

from news import etf
from news.etf import BtcEtf, EtfError, fetch, parse_summary, read_key, unwrap

FUNDS = [{"ticker": "FBTC", "name": "Fidelity Wise Origin Bitcoin Fund", "exchange": "CBOE"},
         {"ticker": "IBIT", "name": "iShares Bitcoin Trust", "exchange": "NASDAQ"},
         {"ticker": "BRRR", "name": "CoinShares Bitcoin ETF", "exchange": "NASDAQ"}]
SNAPS = {
    "IBIT": {"date": "2026-11-20", "ticker": "IBIT", "sponsor_fee": 0.0025, "net_inflow": -120000000,
             "cum_inflow": "61000000000", "net_assets": 82000000000, "mkt_price": 52.1, "prem_dsc": -0.0004,
             "value_traded": 3100000000, "volume": 59000000},
    "FBTC": {"date": 1795392000000, "ticker": "FBTC", "sponsor_fee": 0.0025, "net_inflow": 15000000,
             "cum_inflow": 11000000000, "net_assets": 19000000000, "mkt_price": 90.4, "prem_dsc": 0.0002,
             "value_traded": 500000000, "volume": 5500000},
}
SUMMARY = [   # newest first, as SoSoValue sends it
    {"date": "2026-11-20", "total_net_inflow": -98000000, "total_value_traded": 4200000000,
     "total_net_assets": 120000000000, "cum_net_inflow": 60000000000},
    {"date": "2026-11-19", "total_net_inflow": 45000000.5, "total_value_traded": 3900000000,
     "total_net_assets": 121000000000, "cum_net_inflow": 60098000000},
]


def wrap(data):
    return {"code": 0, "message": "success", "data": data}


def client(routes: dict, seen: list | None = None):
    def handler(req: httpx.Request):
        if seen is not None:
            seen.append((req.url.path, req.headers.get("x-soso-api-key")))
        path = req.url.path.removeprefix("/openapi/v1")
        status, body = routes.get(path, (404, {"code": 400402, "message": "Endpoint not found"}))
        return httpx.Response(status, json=body)
    return httpx.Client(base_url=etf.API, transport=httpx.MockTransport(handler), headers={"x-soso-api-key": "k"})


def good_routes():
    routes = {"/etfs": (200, wrap(FUNDS)), "/etfs/summary-history": (200, wrap(SUMMARY))}
    routes.update({f"/etfs/{t}/market-snapshot": (200, wrap(s)) for t, s in SNAPS.items()})
    return routes


def test_fetch_builds_the_table_largest_fund_first():
    seen = []
    out = fetch("k", client(good_routes(), seen))
    assert [f["ticker"] for f in out["funds"]] == ["IBIT", "FBTC", "BRRR"]
    ibit = out["funds"][0]
    assert ibit["cum_inflow"] == 61e9 and ibit["fee"] == 0.0025 and ibit["date"] == "2026-11-20"
    assert out["funds"][1]["date"] == "2026-11-23"                  # a millisecond timestamp works too
    assert out["missing"] == ["BRRR"] and out["funds"][2]["net_assets"] is None   # shown, but empty
    assert out["totals"]["date"] == "2026-11-20" and out["totals"]["net_inflow"] == -98e6
    assert out["history"] == [["2026-11-19", 45000000.5], ["2026-11-20", -98e6]]
    assert all(key == "k" for _, key in seen)


def test_fetch_explains_a_refused_key_and_the_rate_limit():
    with pytest.raises(EtfError, match="refused the API key"):
        fetch("k", client({"/etfs": (401, {"code": 400101, "message": "API Key is invalid"})}))
    with pytest.raises(EtfError, match="20 requests a minute"):
        fetch("k", client({"/etfs": (429, {"code": 42901, "message": "Rate limit exceeded"})}))


def test_fetch_stops_at_the_rate_limit_instead_of_asking_for_the_rest():
    routes, seen = good_routes(), []
    routes["/etfs/IBIT/market-snapshot"] = (429, {"code": 42901, "message": "Rate limit exceeded"})
    with pytest.raises(etf.EtfAbort, match="20 requests a minute"):
        fetch("k", client(routes, seen))
    asked = [path for path, _ in seen]
    assert asked[-1].endswith("/IBIT/market-snapshot")              # FBTC, then IBIT refused: stop there
    assert not any(p.endswith("/BRRR/market-snapshot") for p in asked)


def test_fetch_fails_when_most_funds_have_no_figures():
    routes = good_routes()
    del routes["/etfs/IBIT/market-snapshot"]                       # 2 of 3 funds now have no figures
    with pytest.raises(EtfError, match="no figures for 2 of 3 funds"):
        fetch("k", client(routes))


def test_a_half_failed_refresh_keeps_the_last_complete_table():
    clock, answers = Clock(), [{"funds": [{"ticker": "IBIT", "net_assets": 1.0}], "missing": []}]

    def get(key):
        if not answers:
            raise EtfError("SoSoValue gave no figures for 2 of 3 funds")
        return answers.pop()

    e = BtcEtf(get=get, key=lambda: "k", clock=clock)
    e.snapshot()
    clock.t += etf.TTL
    s = e.snapshot()
    assert s["funds"][0]["net_assets"] == 1.0 and s["missing"] == []


def test_fetch_rejects_a_changed_fund_list():
    with pytest.raises(EtfError, match="has changed"):
        fetch("k", client({"/etfs": (200, wrap([{"name": "no ticker"}]))}))


def test_unwrap_reads_the_wrapper_and_its_errors():
    assert unwrap(wrap([1])) == [1] and unwrap([1]) == [1]
    with pytest.raises(EtfError, match="Bad thing"):
        unwrap({"code": 500001, "message": "Bad thing"})


def test_parse_summary_skips_rows_without_a_flow():
    totals, history = parse_summary([{"date": "2026-11-21", "total_net_inflow": None}] + SUMMARY)
    assert totals["date"] == "2026-11-20" and len(history) == 2


def test_read_key_from_dotenv_and_prefers_the_environment(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    monkeypatch.delenv(etf.KEY_ENV, raising=False)
    assert read_key(path) is None                                   # no .env
    path.write_text("# SoSoValue\nSOSOVALUE_API_KEY=\n", encoding="utf-8")
    assert read_key(path) is None                                   # left blank
    path.write_text('﻿# SoSoValue\nOTHER=1\nexport SOSOVALUE_API_KEY = "file-key"\n', encoding="utf-8")
    assert read_key(path) == "file-key"
    monkeypatch.setenv(etf.KEY_ENV, "env-key")
    assert read_key(path) == "env-key"


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def test_snapshot_without_a_key_asks_for_one():
    s = BtcEtf(get=lambda key: pytest.fail("no fetch without a key"), key=lambda: None).snapshot()
    assert s["needs_key"] and s["funds"] == [] and s["key_url"].startswith("https://sosovalue.com")


def test_snapshot_caches_waits_after_a_failure_and_keeps_the_last_answer():
    calls, clock, fail = [], Clock(), []

    def get(key):
        calls.append(key)
        if fail:
            raise EtfError("down")
        return {"funds": [{"ticker": "IBIT"}], "totals": None, "history": [], "missing": []}

    e = BtcEtf(get=get, key=lambda: "k", clock=clock)
    assert e.snapshot()["funds"][0]["ticker"] == "IBIT" and e.snapshot()["error"] is None
    assert calls == ["k"]                                   # reused
    clock.t += etf.TTL
    fail.append(True)
    s = e.snapshot()                                        # stale and failing: last answer still shown
    assert len(calls) == 2 and s["funds"][0]["ticker"] == "IBIT"
    e.snapshot()
    assert len(calls) == 2                                  # no retry straight after a failure
    clock.t += etf.RETRY_AFTER
    e.snapshot()
    assert len(calls) == 3


def test_snapshot_reports_an_error_when_there_is_nothing_to_show():
    def get(key):
        raise EtfError("Couldn't reach SoSoValue (ConnectError)")
    s = BtcEtf(get=get, key=lambda: "k").snapshot()
    assert s["funds"] == [] and s["error"].startswith("Couldn't reach") and not s["needs_key"]
