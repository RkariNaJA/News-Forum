"""Live check of the click-a-row → day chart buttons on Crypto Prices and Stock Prices.

The quotes table is TradingView's iframe; web/prices.js lays invisible buttons over its rows at fixed
offsets (QUOTE_ROW). If TradingView changes its layout, a click lands on the wrong row. This test loads
the real widget and checks, for every button, that the row under its top, middle and bottom is the
symbol the button opens. Needs internet and Microsoft Edge (or Playwright's Chromium):

    py -3.13 -m pip install playwright
    py -3.13 -m pytest --live tests/test_price_rows_live.py
"""
import json
import socket
import threading
import time

import pytest
import uvicorn

from news.server import create_app

pytestmark = pytest.mark.live

WIDGET_TIMEOUT_MS = 45_000


@pytest.fixture(scope="module")
def app_url(tmp_path_factory):
    """The real page and scripts, served on a free port with an empty feed list and a throwaway database."""
    tmp = tmp_path_factory.mktemp("live")
    feeds = tmp / "feeds.json"
    feeds.write_text(json.dumps({"feeds": []}), encoding="utf-8")
    app = create_app(feeds, tmp / "news.db", fetcher=lambda todo: {})
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        if time.time() > deadline:
            pytest.fail("test server did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api", reason="pip install playwright")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="msedge")   # Edge comes with Windows: no browser download
        except Exception:
            b = p.chromium.launch()                     # else Playwright's own Chromium, if installed
        yield b
        b.close()


def open_price_page(browser, url, view, width):
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.goto(url)
    page.evaluate("(v) => selectTab(v)", view)
    names = page.locator(".quote-row").evaluate_all(
        "bs => bs.map(b => b.getAttribute('aria-label').replace('Day chart: ', ''))")
    assert names, f"no row buttons on {view}"
    # Wait for TradingView's iframe to draw one link per symbol.
    frame = next(f for f in _wait_frames(page) if "market-quotes" in f.url)
    frame.wait_for_function(
        "n => [...document.querySelectorAll('a')].filter(a => a.href.includes('symbol')).length >= n",
        arg=len(names), timeout=WIDGET_TIMEOUT_MS)
    return page, frame, names


def _wait_frames(page):
    deadline = time.time() + WIDGET_TIMEOUT_MS / 1000
    while time.time() < deadline:
        if any("market-quotes" in f.url for f in page.frames):
            return page.frames
        page.wait_for_timeout(200)
    pytest.fail("TradingView quotes iframe never loaded")


ROW_UNDER_POINT = """([x, y]) => {
  let e = document.elementFromPoint(x, y);
  for (let i = 0; i < 8 && e && !e.querySelector?.('a'); i++) e = e.parentElement;
  return e?.querySelector('a')?.textContent.trim() || null;
}"""


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("view", ["prices", "stocks"])
def test_every_row_button_sits_on_its_own_row(browser, app_url, view, width):
    page, frame, names = open_price_page(browser, app_url, view, width)
    try:
        iframe_top = page.locator("#prices-widget iframe").bounding_box()["y"]
        boxes = page.locator(".quote-row").evaluate_all(
            "bs => bs.map(b => { const r = b.getBoundingClientRect(); return [r.top, r.bottom]; })")
        wrong = []
        for name, (top, bottom) in zip(names, boxes):
            for y in (top + 3, (top + bottom) / 2, bottom - 3):
                got = frame.evaluate(ROW_UNDER_POINT, [60, y - iframe_top])
                if got != name:
                    wrong.append(f"{name}: at y={y - iframe_top:.0f} the widget shows {got!r}")
        assert not wrong, "row buttons are off; re-measure QUOTE_ROW in web/prices.js:\n" + "\n".join(wrong)
    finally:
        page.close()


def test_clicking_a_row_opens_the_day_chart_not_a_tab(browser, app_url):
    page, _, names = open_price_page(browser, app_url, "stocks", 1280)
    try:
        tabs_before = len(page.context.pages)
        page.locator(".quote-row").nth(1).click()
        page.wait_for_selector("#chart-box iframe", timeout=WIDGET_TIMEOUT_MS)
        assert page.evaluate("document.querySelector('#chart-dialog').open")
        assert page.text_content("#chart-title") == names[1]
        assert page.text_content("#chart-symbol").endswith("Day chart")
        assert len(page.context.pages) == tabs_before
        page.keyboard.press("Escape")
        assert not page.evaluate("document.querySelector('#chart-dialog').open")
        assert page.locator("#chart-box iframe").count() == 0
    finally:
        page.close()
