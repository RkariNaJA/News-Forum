from pathlib import Path

import pytest

from news.goldth import GoldTh, GoldThError, parse

PAGE = (Path(__file__).parent / "fixtures" / "goldth.html").read_text(encoding="utf-8")


def test_parse_reads_the_announcement_box():
    latest = parse(PAGE)["latest"]
    assert latest == {"time": "2026-11-26T09:57:00+07:00", "round": 9,          # Buddhist year 2569 = 2026
                      "bar_buy": 57550.0, "bar_sell": 57750.0, "ornament_buy": 56395.2, "ornament_sell": 58550.0,
                      "change_today": 550.0, "change": -50.0}


def test_parse_reads_todays_rounds_newest_first_with_the_box_on_top():
    rounds = parse(PAGE)["rounds"]
    assert [r["round"] for r in rounds] == [9, 8, 7, 6]     # the table stopped at 8; 9 comes from the box
    assert rounds[0]["spot"] is None and rounds[0]["change"] == -50.0
    assert rounds[1] == {"time": "2026-11-26T09:54:00+07:00", "round": 8, "bar_buy": 57600.0, "bar_sell": 57800.0,
                         "ornament_buy": 56440.68, "ornament_sell": 58600.0, "spot": 3593.0, "thb": 33.99,
                         "change": -100.0}                  # direction from the arrow image (img-down)
    assert rounds[3]["change"] == 100.0                     # img-up


def test_parse_does_not_repeat_a_round_the_table_already_has():
    page = PAGE.replace("(ครั้งที่ 9)", "(ครั้งที่ 8)")
    assert [r["round"] for r in parse(page)["rounds"]] == [8, 7, 6]


@pytest.mark.parametrize("bad", ["", "<html><body>Maintenance</body></html>",
                                 PAGE.replace("พฤศจิกายน", "November")])
def test_parse_rejects_a_changed_page(bad):
    with pytest.raises(GoldThError):
        parse(bad)


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def test_snapshot_caches_and_keeps_the_last_answer_on_failure():
    calls, clock, fail = [], Clock(), []

    def get():
        calls.append(1)
        if fail:
            raise GoldThError("down")
        return parse(PAGE)

    g = GoldTh(get=get, clock=clock)
    assert g.snapshot()["latest"]["round"] == 9 and g.snapshot()["error"] is None
    assert len(calls) == 1                            # reused
    clock.t, fail[:] = 301, [True]
    s = g.snapshot()                                  # stale and failing: last answer still shown
    assert len(calls) == 2 and s["latest"]["round"] == 9 and s["error"] is None


def test_snapshot_reports_an_error_when_there_is_nothing_to_show():
    def get():
        raise GoldThError("Couldn't reach ทองคำราคา.com (ConnectError)")
    s = GoldTh(get=get).snapshot()
    assert s["latest"] is None and s["rounds"] == [] and s["error"].startswith("Couldn't reach")


@pytest.mark.live
def test_live_site_still_parses():
    """The real page: catches a redesign of ทองคำราคา.com (run with --live)."""
    from news.goldth import fetch
    d = fetch()
    assert 10_000 < d["latest"]["bar_sell"] < 500_000 and d["latest"]["bar_buy"] < d["latest"]["bar_sell"]
    assert d["rounds"] and d["rounds"][0]["round"] == max(r["round"] for r in d["rounds"])
