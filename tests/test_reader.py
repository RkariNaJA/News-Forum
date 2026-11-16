import httpx
import pytest

from news.reader import MIN_TEXT_CHARS, ReaderError, check_url, download, extract
from conftest import FIXTURES

ARTICLE = (FIXTURES / "article.html").read_text(encoding="utf-8")
URL = "https://news.example.com/world/trade-deal"


def test_extract_keeps_story_and_drops_page_chrome():
    out = extract(ARTICLE, URL)
    text = " ".join(out["paragraphs"])
    assert out["paragraphs"][0].startswith("Leaders from twelve countries agreed on Sunday")
    assert "ratified by each country's parliament" in text
    for junk in ("cookies", "Subscribe", "newsletter", "All rights reserved"):
        assert junk not in text
    assert out["author"] == "Jane Reporter"
    assert out["image"] == "https://img.example.com/trade-large.jpg"
    assert out["date"] == "2026-11-15"


def test_short_page_counts_as_paywall():
    teaser = "<html><body><article><p>Subscribe to read the rest of this story.</p></article></body></html>"
    with pytest.raises(ReaderError, match="paywall"):
        extract(teaser, URL)
    assert MIN_TEXT_CHARS > len("Subscribe to read the rest of this story.")


def _page(body: str) -> str:
    return f"<html><head><title>Story</title></head><body><main><article>{body}</article></main></body></html>"


LONG = ("The council voted on Tuesday to rebuild the old bridge after engineers found deep cracks "
        "in two of its supports during a routine inspection earlier this year. ")


def test_leading_labels_are_skipped_and_list_markers_removed():
    body = ("<ul><li>Published</li></ul>" + f"<p>{LONG * 3}</p>"
            + "<ul><li>The first point made in a list inside the story</li></ul>" + f"<p>{LONG * 2}</p>")
    ps = extract(_page(body), URL)["paragraphs"]
    assert ps[0].startswith("The council voted")
    assert "The first point made in a list inside the story" in ps   # kept, without the "- "
    assert not any(p.startswith("- ") for p in ps)


def test_mostly_list_page_is_not_an_article():
    items = "".join(f"<li>Episode {i}: a long episode title about technology and science {i}</li>" for i in range(20))
    with pytest.raises(ReaderError, match="list of links"):
        extract(_page(f"<p>Episodes</p><ul>{items}</ul>"), URL)


@pytest.mark.parametrize("bad", [
    "javascript:alert(1)", "file:///C:/Windows/win.ini", "http://localhost:8770/api/status",
    "http://127.0.0.1/", "http://192.168.1.10/admin", "http://10.0.0.5/", "http://[::1]/",
    "http://printer.local/", "",
])
def test_check_url_refuses_local_and_odd_urls(bad):
    with pytest.raises(ReaderError):
        check_url(bad)


def test_check_url_allows_public_sites():
    check_url("https://www.bbc.co.uk/news/articles/abc")
    check_url("http://8.8.8.8/page")


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True,
                        event_hooks={"request": [lambda req: check_url(str(req.url))]})


def test_download_maps_refusals_to_readable_errors():
    with _client(lambda req: httpx.Response(403, text="nope")) as c:
        with pytest.raises(ReaderError, match="refused"):
            download(URL, c)
    with _client(lambda req: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")) as c:
        with pytest.raises(ReaderError, match="not a web page"):
            download(URL, c)


def test_download_returns_html():
    with _client(lambda req: httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                                            text=ARTICLE)) as c:
        assert "Leaders agree on trade deal" in download(URL, c)


def test_redirect_to_local_address_is_refused():
    def handler(req):
        if req.url.host == "news.example.com":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8770/api/status"})
        return httpx.Response(200, text="secret")
    with _client(handler) as c:
        with pytest.raises(ReaderError, match="Local"):
            download(URL, c)
