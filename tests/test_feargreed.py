import pytest

from news.feargreed import FearGreed, FearGreedError, parse

# Shaped like api.alternative.me/fng/?limit=0 (newest first; only the newest row has time_until_update).
PAYLOAD = {"name": "Fear and Greed Index", "data": [
    {"value": "11", "value_classification": "Extreme Fear", "timestamp": "1795392000", "time_until_update": "3600"},
    {"value": "12", "value_classification": "Extreme Fear", "timestamp": "1795305600"},
    {"value": "54", "value_classification": "Neutral", "timestamp": "1795219200"},
], "metadata": {"error": None}}


def test_parse_orders_history_oldest_first_and_reads_today():
    out = parse(PAYLOAD, now=1795400000)
    assert out["history"] == [["2026-11-21", 54], ["2026-11-22", 12], ["2026-11-23", 11]]
    assert out["current"] == {"date": "2026-11-23", "value": 11, "label": "Extreme Fear"}
    assert out["next_update"] == "2026-11-23T03:13:20+00:00"        # now + time_until_update (1 h)


@pytest.mark.parametrize("bad", [{}, {"data": [{"value": "x", "timestamp": "1"}]}, {"data": []}, {"data": None}])
def test_parse_rejects_changed_data(bad):
    with pytest.raises(FearGreedError):
        parse(bad)


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def test_snapshot_caches_for_an_hour_and_keeps_the_last_answer_on_failure():
    calls, clock, fail = [], Clock(), []

    def get():
        calls.append(1)
        if fail:
            raise FearGreedError("down")
        return parse(PAYLOAD)

    fg = FearGreed(get=get, clock=clock)
    assert fg.snapshot()["current"]["value"] == 11 and fg.snapshot()["error"] is None
    assert len(calls) == 1                            # reused
    clock.t, fail[:] = 3601, [True]
    s = fg.snapshot()                                 # stale and failing: last answer still shown
    assert len(calls) == 2 and s["current"]["value"] == 11 and s["error"] is None


def test_snapshot_reports_an_error_when_there_is_nothing_to_show():
    def get():
        raise FearGreedError("Couldn't reach alternative.me (ConnectError)")
    s = FearGreed(get=get).snapshot()
    assert s["current"] is None and s["history"] == [] and s["error"].startswith("Couldn't reach")
