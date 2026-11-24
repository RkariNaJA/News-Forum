"""Live check of every source in feeds.json: one test per feed, so a failure names the feed and why.

    py -3.13 -m pytest --live -q tests/test_feeds_live.py

Needs internet only (no browser). It goes through fetch_all, so it uses the app's real client settings
(User-Agent, timeout, redirects): it would have caught the Guardian's 403 of 24 Nov 2026 in seconds.
"""
import time

import pytest

from news import config
from news.feeds import fetch_all, load_feeds

FEEDS = load_feeds(config.FEEDS_PATH)


@pytest.mark.live
@pytest.mark.parametrize("feed", FEEDS, ids=[f["name"] for f in FEEDS])
def test_feed_returns_stories(feed):
    articles, error = fetch_all([feed])[feed["name"]]
    if error:   # one retry: a single network blip (seen on 24 Nov) is not a broken feed
        first = error
        time.sleep(3)
        articles, error = fetch_all([feed])[feed["name"]]
        if error:
            error = f"{error} (and before that: {first})" if error != first else f"{error} (twice)"
    assert error is None, f"{feed['name']}: {error}  ({feed['url']})"
    assert articles, f"{feed['name']}: no stories  ({feed['url']})"
