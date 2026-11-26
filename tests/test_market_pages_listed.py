"""Every market page in PRICE_PAGES (web/prices.js) must be on the Markets menu and in the docs.

A new page is named in several places, and the docs were missed more than once. These tests read the
files as text, so they need no browser and no network. The page's name is its Markets menu label.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                "eleven", "twelve"]
# Places that name two pages together: the label counts as present if this text is there.
SHARED_NAME = {"Crypto Prices": "Crypto / Stock Prices", "Stock Prices": "Crypto / Stock Prices"}


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def price_pages() -> list[str]:
    js = read("web/prices.js")
    body = js[js.index("const PRICE_PAGES = {"):]
    body = body[:body.index("\n};")]
    return re.findall(r"^  (\w+): \{", body, re.M)


def menu_labels() -> dict[str, str]:
    html = read("web/index.html")
    menu = html[html.index('id="market-tabs"'):]
    menu = menu[:menu.index("</div>")]
    return {view: label.strip() for view, label in
            re.findall(r'<button [^>]*data-view="(\w+)"[^>]*>([^<]+)</button>', menu)}


def blockquote_intro(text: str) -> str:
    """The '> ...' note at the top of a guide, as one line."""
    return " ".join(line[1:].strip() for line in text.splitlines() if line.startswith(">"))


def section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start:] if end < 0 else text[start:end]


def named(label: str, text: str) -> bool:
    return label in text or SHARED_NAME.get(label, "\0") in text


PAGES = price_pages()
LABELS = menu_labels()


def test_price_pages_are_found():
    assert len(PAGES) >= 7, PAGES   # guards the parsing above


def test_every_page_has_a_markets_menu_button_and_no_extra_buttons():
    assert sorted(LABELS) == sorted(PAGES), "index.html #market-tabs buttons must match PRICE_PAGES"


@pytest.mark.parametrize("view", PAGES)
def test_page_is_named_everywhere(view):
    label = LABELS.get(view)
    assert label, f"no Markets menu button with data-view=\"{view}\" in index.html"
    html = read("web/index.html")
    tooltip = re.search(r'id="markets-toggle"[^>]*title="([^"]+)"', html).group(1)
    readme = read("README.md")
    market = read("docs/MARKET-PAGES.md")
    found = {
        "index.html: the Markets button's title": named(label, tooltip),
        "README.md: a row of the market pages table (| **Name** |)": f"| **{label}** |" in readme,
        "README.md: a screenshot captioned <b>Name</b>": f"<b>{label}</b>" in readme,
        "docs/MARKET-PAGES.md: the note at the top": named(label, blockquote_intro(market)),
        "docs/MARKET-PAGES.md: a ## section heading": named(label, "\n".join(re.findall(r"^## .*$", market, re.M))),
        "docs/DEVELOPER-GUIDE.md: the note at the top": named(label, blockquote_intro(read("docs/DEVELOPER-GUIDE.md"))),
        "docs/Diagram Flow.md: the market pages diagram":
            named(label, section(read("docs/Diagram Flow.md"), "## 5. Market pages")),
    }
    missing = [where for where, ok in found.items() if not ok]
    assert not missing, f"'{label}' is missing from: " + "; ".join(missing)


def test_market_pages_guide_counts_the_pages():
    word = NUMBER_WORDS[len(PAGES)]
    assert f"The {word} pages" in read("docs/MARKET-PAGES.md"), f"MARKET-PAGES.md should say 'The {word} pages'"
