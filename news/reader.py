"""Reader view: download one article page and extract just the story text (plain paragraphs)."""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

import httpx
import trafilatura

# A normal browser UA: several publishers refuse unknown clients for article pages.
PAGE_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
PAGE_TIMEOUT = 20.0
MAX_PAGE_BYTES = 5_000_000
MIN_TEXT_CHARS = 400        # less than this is a paywall teaser or a failed extraction
LEAD_MIN_CHARS = 30         # shorter lines before the first paragraph are page labels
MAX_LIST_SHARE = 0.6        # mostly bullet lines = an episode list / index page, not a story
MAX_PARAGRAPHS = 80
MAX_TEXT_CHARS = 40_000


class ReaderError(Exception):
    """The article could not be fetched or no readable story text was found."""


def check_url(url: str) -> None:
    """Allow only public http(s) URLs, never this PC or the local network."""
    parts = urlsplit(url or "")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ReaderError("Not a web link")
    host = parts.hostname.lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ReaderError("Local addresses are not fetched")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if not ip.is_global:
        raise ReaderError("Local addresses are not fetched")


def download(url: str, client: httpx.Client | None = None) -> str:
    """Fetch the page HTML, refusing huge responses and non-HTML content."""
    check_url(url)
    own = client is None
    client = client or httpx.Client(
        timeout=PAGE_TIMEOUT, follow_redirects=True, max_redirects=5,
        headers={"User-Agent": PAGE_USER_AGENT, "Accept": "text/html,application/xhtml+xml",
                 "Accept-Language": "en-US,en;q=0.9"},
        # every hop of a redirect chain is checked, not just the first and last
        event_hooks={"request": [lambda req: check_url(str(req.url))]})
    try:
        with client.stream("GET", url) as resp:
            if resp.status_code in (401, 402, 403, 405, 429, 451):
                raise ReaderError(f"The site refused the request ({resp.status_code})")
            if resp.status_code >= 400:
                raise ReaderError(f"The site returned an error ({resp.status_code})")
            ctype = resp.headers.get("content-type", "")
            if ctype and "html" not in ctype:
                raise ReaderError("The link is not a web page")
            body = bytearray()
            for chunk in resp.iter_bytes():
                body += chunk
                if len(body) > MAX_PAGE_BYTES:
                    raise ReaderError("The page is too large")
            return body.decode(resp.encoding or "utf-8", errors="replace")
    except httpx.HTTPError as exc:
        raise ReaderError(f"Couldn't reach the site ({type(exc).__name__})") from exc
    finally:
        if own:
            client.close()


def extract(html: str, url: str) -> dict:
    """Pull the main story out of a page. Returns paragraphs (plain text) and page metadata."""
    doc = trafilatura.bare_extraction(html, url=url, include_comments=False, include_tables=False,
                                      include_images=False, favor_precision=True, with_metadata=True)
    data = doc.as_dict() if hasattr(doc, "as_dict") else (doc or {})
    text = (data.get("text") or "").strip()
    # The pop-up shows its own headline and byline, so drop them when they lead the text.
    skip = {_norm(data.get("title")), _norm(data.get("author")), _norm(f"By {data.get('author')}")} - {""}
    paragraphs, total, list_chars = [], 0, 0
    for line in text.split("\n"):
        line = " ".join(line.split())
        is_item = line.startswith("- ")
        if is_item:
            line = line[2:].strip()
        if not line:
            continue
        # Before the story starts, skip the headline, byline and short page labels ("Published").
        if not paragraphs and (_norm(line) in skip or len(line) < LEAD_MIN_CHARS):
            continue
        paragraphs.append(line)
        total += len(line)
        list_chars += len(line) if is_item else 0
        if len(paragraphs) >= MAX_PARAGRAPHS or total >= MAX_TEXT_CHARS:
            break
    if total < MIN_TEXT_CHARS:
        raise ReaderError("No story text on the page (it may be a video, or behind a paywall)")
    if list_chars > MAX_LIST_SHARE * total:
        raise ReaderError("This page is a video or a list of links, not an article")
    image = data.get("image")
    if image and urlsplit(image).scheme not in ("http", "https"):
        image = None
    return {"paragraphs": paragraphs, "author": data.get("author") or None,
            "date": data.get("date") or None, "image": image}


def _norm(value) -> str:
    """Letters and digits only, lower case: quotes, dashes and spacing differences don't count."""
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def same_text(a: str, b: str) -> bool:
    return bool(_norm(a)) and _norm(a) == _norm(b)


def read_article(url: str) -> dict:
    """Download + extract. Raises ReaderError with a short, human message on failure."""
    return extract(download(url), url)
