from datetime import date, datetime, timezone

import pytest

from news.fedwatch import (FedWatch, FedWatchError, contract, meeting_rates, outcome_odds,
                           parse_calendar)


def _year(year, rows):
    cells = "".join(f'<div class="fomc-meeting__month col-xs-5"><strong>{m}</strong></div>'
                    f'<div class="fomc-meeting__date col-xs-4">{d}</div>' for m, d in rows)
    return f'<h4><a id="{year}">{year} FOMC Meetings</a></h4><div class="panel">{cells}</div>'


# Shaped like federalreserve.gov/monetarypolicy/fomccalendars.htm (newest year first).
CALENDAR = (_year(2027, [("January", "26-27"), ("March", "16-17*")])
            + _year(2026, [("October", "27-28"), ("November", "4 (notation vote)"), ("December", "8-9*")])
            + _year(2024, [("Apr/May", "30-1"), ("July", "30-31")]))


def test_calendar_parsing():
    ms = parse_calendar(CALENDAR)
    assert [m["date"] for m in ms] == ["2024-05-01", "2024-07-31", "2026-10-28", "2026-12-09",
                                       "2027-01-27", "2027-03-17"]       # notation vote left out
    dec = ms[3]
    assert dec["label"] == "8-9 Dec" and dec["sep"] is True and ms[2]["sep"] is False
    assert ms[0]["label"] == "30-1 Apr/May"                              # ends in the second month
    # 2:00 pm Eastern: 19:00 UTC in winter, 18:00 UTC in summer time
    assert dec["decision"] == "2026-12-09T19:00:00+00:00"
    assert ms[1]["decision"] == "2024-07-31T18:00:00+00:00"


def test_contract_symbols():
    assert contract(2026, 12) == "ZQZ26" and contract(2027, 1) == "ZQF27" and contract(2026, 11) == "ZQX26"


def test_odds_split_between_the_two_nearest_steps():
    # -0.784 steps: 78.4 % for a 25 bp cut, 21.6 % for no change
    out = outcome_odds(3.88, 3.88 - 0.196, 3.75, 4.00)
    assert [(o["low"], o["high"], o["move_bp"]) for o in out] == [(3.5, 3.75, -25), (3.75, 4.0, 0)]
    assert [o["prob"] for o in out] == [0.784, 0.216]
    # an exact whole step is one outcome at 100 %
    assert outcome_odds(3.88, 4.13, 3.75, 4.00) == [{"move_bp": 25, "low": 4.0, "high": 4.25, "prob": 1.0}]


def _prices(table):
    return lambda symbol: table[symbol]


def test_rates_anchored_on_a_quiet_previous_month():
    # Meeting on 9 Dec (31 days): 9 days at the old rate, 22 at the new. November has no meeting.
    start, end, anchor = meeting_rates(date(2026, 12, 9), {(2026, 10), (2026, 12)},
                                       _prices({"ZQX26": 96.12, "ZQZ26": 100 - (3.88 * 9 + 4.13 * 22) / 31}), 3.88)
    assert anchor == "previous month" and start == pytest.approx(3.88) and end == pytest.approx(4.13)


def test_rates_anchored_on_a_quiet_next_month():
    # 27 Jan 2027: December has a meeting, February doesn't.
    jan_avg = (4.10 * 27 + 3.85 * 4) / 31
    start, end, anchor = meeting_rates(date(2027, 1, 27), {(2026, 12), (2027, 1), (2027, 3)},
                                       _prices({"ZQF27": 100 - jan_avg, "ZQG27": 96.15}), 4.10)
    assert anchor == "next month" and start == pytest.approx(4.10) and end == pytest.approx(3.85)


def test_meeting_on_the_last_day_uses_the_next_month():
    start, end, anchor = meeting_rates(date(2024, 7, 31), {(2024, 6), (2024, 7), (2024, 9)},
                                       _prices({"ZQN24": 94.67, "ZQQ24": 94.92}), 5.33)
    assert anchor == "next month" and start == pytest.approx(5.33) and end == pytest.approx(5.08)


def test_busy_months_on_both_sides_fall_back_to_todays_rate():
    start, end, anchor = meeting_rates(date(2026, 6, 10), {(2026, 5), (2026, 6), (2026, 7)},
                                       _prices({"ZQM26": 100 - (4.0 * 10 + 3.75 * 20) / 30}), 4.0)
    assert anchor == "today's rate" and end == pytest.approx(3.75)


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


RATE = {"low": 3.75, "high": 4.0, "effr": 3.88, "as_of": "2026-11-19"}
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


def _watch(calls, clock, fail=()):
    def source(name, value):
        def get():
            calls.append(name)
            if name in fail:
                raise FedWatchError(f"{name} down")
            return value
        return get
    quotes = {"ZQX26": 96.12, "ZQZ26": 100 - (3.88 * 9 + 4.13 * 22) / 31, "ZQF27": 95.87, "ZQG27": 95.87}
    return FedWatch(get_calendar=source("calendar", parse_calendar(CALENDAR)), get_rate=source("rate", RATE),
                    get_quote=lambda s: (calls.append(s), {"symbol": s, "price": quotes[s], "time": "t"})[1],
                    clock=clock)


def test_snapshot_next_meeting_odds_and_caching():
    calls, clock = [], Clock()
    fw = _watch(calls, clock)
    s = fw.snapshot(now=NOW)
    assert s["next"]["date"] == "2026-12-09" and [m["date"] for m in s["upcoming"]] == ["2027-01-27", "2027-03-17"]
    assert s["errors"] == {} and s["target"] == RATE
    assert [(o["move_bp"], o["prob"]) for o in s["odds"]["outcomes"]] == [(25, 1.0)]
    assert [q["symbol"] for q in s["odds"]["contracts"]] == ["ZQX26", "ZQZ26"]
    fw.snapshot(now=NOW)                       # everything reused
    assert calls == ["calendar", "rate", "ZQZ26", "ZQX26"]
    clock.t = 11 * 60                          # quotes are older than 10 minutes: only they are fetched again
    fw.snapshot(now=NOW)
    assert calls[4:] == ["ZQZ26", "ZQX26"]


def test_snapshot_skips_past_meetings():
    s = _watch([], Clock()).snapshot(now=datetime(2026, 12, 9, 19, 1, tzinfo=timezone.utc))
    assert s["next"]["date"] == "2027-01-27"


def test_a_failing_source_is_reported_and_the_rest_still_shows():
    s = _watch([], Clock(), fail=("rate",)).snapshot(now=NOW)
    assert s["next"]["date"] == "2026-12-09" and s["odds"] is None and s["errors"] == {"rate": "rate down"}
    s = _watch([], Clock(), fail=("calendar",)).snapshot(now=NOW)
    assert s["next"] is None and s["errors"] == {"calendar": "calendar down"}


def test_last_good_answer_is_used_when_a_source_fails_later():
    calls, clock = [], Clock()
    fw = _watch(calls, clock)
    fw.snapshot(now=NOW)
    fw._sources["rate"] = (lambda: (_ for _ in ()).throw(FedWatchError("down")), 0)   # always stale, now failing
    s = fw.snapshot(now=NOW)
    assert s["target"] == RATE and "rate" not in s["errors"]
