# News Forum

**Turns 25 international news RSS feeds into one quiet, newspaper-style front page on your own PC.**

<p>
  <img src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white" alt="Python 3.13">
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/feedparser-6.0-4B8BBE" alt="feedparser 6.0">
  <img src="https://img.shields.io/badge/trafilatura-2.3-6A5ACD" alt="trafilatura 2.3">
  <img src="https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/JavaScript-vanilla-F7DF1E?logo=javascript&logoColor=black" alt="Vanilla JavaScript">
  <img src="https://img.shields.io/badge/RSS-25%20feeds-FFA500?logo=rss&logoColor=white" alt="RSS: 25 feeds">
  <img src="https://img.shields.io/badge/tests-57%20passing-2EA44F?logo=pytest&logoColor=white" alt="tests: 57 passing">
  <img src="https://img.shields.io/badge/runs-localhost%20only-555555" alt="runs on localhost only">
</p>

A personal daily reader for world, business, crypto and investing, Asia/ASEAN and AI news. It runs only on
`127.0.0.1`, keeps what you have read and saved in a local SQLite file, and needs no account,
API key or paid news service — just the public RSS feeds the publishers already offer.

```
25 RSS feeds → fetch in parallel → clean + de-duplicate → SQLite → one page with tabs at :8770
```

<p align="center">
  <img src="Pic/Screenshot%202026-11-16%20160250.png" alt="News Forum home page: the Today tab with story cards from Cointelegraph, CoinDesk and Guardian Money" width="900">
</p>
<sub>The <b>Today</b> tab: every source mixed, newest first. Faded cards are stories already read; unread counts sit on each tab.</sub>

## The problem it solves

Keeping up with international news meant opening the same handful of sites every morning, each with
its own layout, autoplay video, cookie banner and "recommended for you" rail, and no memory of which
stories you had already seen yesterday.

News Forum pulls the headlines from all of those outlets into one list and gets the fiddly parts right:

- **Same story, one row.** Links are normalised (tracking parameters such as `utm_*` and BBC's
  `at_*` are stripped) before they are stored, so a story carried by two BBC feeds shows once.
- **It remembers you.** Read stories fade, unread counts sit on each tab, and starred stories stay
  in **Saved** even after the clean-up removes everything else.
- **Only the last 3 days.** Stories older than 3 days are skipped when feeds are fetched and removed
  on every refresh, so the tabs stay short. Starred stories are never removed.
- **A broken feed doesn't break the page.** Every source is fetched separately; if one is down you
  get a one-line notice naming it and the rest of the news as usual. A dot at the top right says
  "25 sources OK" or, in red, how many are down; click it for the details.
- **Keyboard-friendly.** `←` `→` switch sections, `j` `k` move between stories, `Enter` opens one,
  `s` saves, `m` marks read, `o` opens the website, `/` searches. Press `?` for the full list.
- **Feeds without dates don't flood the top.** Nikkei Asia publishes no timestamps, so its stories
  are spaced out in feed order instead of all landing at "just now".

## What you get

| Tab | What's in it |
|---|---|
| **Today** | Everything published in the last 24 hours, every section mixed, newest first |
| **World** | BBC World · Al Jazeera · DW · The Guardian · NPR · France 24 |
| **Business** | BBC Business · CNBC · Guardian Business |
| **Crypto & Investing** | CoinDesk · Cointelegraph · Decrypt · CNBC Markets · CNBC Investing · Guardian Money |
| **Crypto Prices** (button, top right) | A live price table for 14 coins (Bitcoin, Ethereum, BNB, Solana, XRP… Optimism (OP), Arbitrum (ARB)) in US dollars: price, change, change %, open, high, low. Click any row for a day chart (daily candles) in a pop-up. It's TradingView's free *Market Quotes* widget, so this tab needs internet and loads from tradingview.com |
| **Stock Prices** (button, top right) | The same price-only table for gold (XAU/USD, live) on top, then 15 US-listed tech stocks: Anthropic (ANT), Apple, Microsoft, Nvidia, Alphabet, Amazon, Meta, Tesla, Broadcom, TSMC, AMD, Oracle, Netflix, ASML, Intel. Free stock data from TradingView is delayed (marked with a small **D**); gold is not. Rows open the same day-chart pop-up |
| **Asia** | CNA · Nikkei Asia · Bangkok Post · The Diplomat · BBC Asia |
| **AI** | The Verge AI · Ars Technica AI · MIT Tech Review AI · Guardian AI · Wired AI |
| **Saved** | Stories you starred, kept until you un-star them |

<p align="center">
  <img src="Pic/Screenshot%202026-11-16%20160319.png" alt="Crypto Prices view: a TradingView price table with value, change, change %, open, high, low and previous close for each coin" width="900">
</p>
<sub><b>Crypto Prices</b> (the dark button at the top right): live prices only, no charts. Taken before OP and ARB were added to the list.</sub>

<p align="center">
  <img src="Pic/Screenshot%202026-11-16%20161738.png" alt="Stock Prices view: gold (XAU/USD) on top, then Apple, Microsoft, Nvidia and other US tech stocks with value, change, open, high, low and previous close" width="900">
</p>
<sub><b>Stock Prices</b>: gold (XAU/USD) on top, then 14 US tech stocks. The small orange <b>D</b> marks delayed stock prices; gold is live.</sub>

Each story is a card: section · source · time ago, the headline (opens the original article in a
new tab and marks it read), the publisher's own short blurb, a thumbnail when the feed has one, and
**☆ Save** / **Mark read** buttons. Above the list: headline search, a source filter, *Hide read*
and *Mark all as read*. Light and dark themes; works at phone width.

**Reader view.** Clicking anywhere on a card except the headline opens a pop-up with the whole
story: the headline, author, full date, tags, a large photo and the article text. The text is pulled
from the publisher's page and shown as plain paragraphs, without menus, ads or cookie banners. A
**Read on [source] ↗** button opens the original. Each article is fetched only when you open it, and
the result is kept, so reopening it is instant.

**Key-sentence highlights.** In the pop-up, the story's most important sentences get a soft marker:
one for a short story, up to three for a long one, never two in the same paragraph or two that make the
same point. A **Highlights** switch turns them off. They're picked on your PC without AI. Every word
gets a weight for how often it appears in this story and how rare it is in the other stories you have
stored (TF-IDF), with a bonus for headline words. The sentences whose words weigh the most win, and the
opening sentence gets a small bonus because news puts the main point first.

When a site blocks this (France 24, The Diplomat, Ars Technica), or the item is a video or TV page,
the pop-up says so and shows everything the feed itself carries. A live check of 54 recent stories
got the full text for 39, and all 6 Crypto & Investing feeds gave full text for 3 of 3 stories when they were added.

A first full refresh on 16 Nov 2026 returned:

```json
{"fetched": 18, "new": 523, "errors": {}}
```

## Running it

```bat
py -3.13 -m pip install -r requirements.txt
"Start News Forum.bat"
```

The launcher runs `py -3.13 -m news` and opens <http://127.0.0.1:8770> in your browser. Opening the
page fetches any source not checked in the last 30 minutes; **Refresh** fetches all of them now.

**Start at login, no window:** put a shortcut in `shell:startup` that runs `pythonw.exe -m news
--no-browser`, with *Start in* set to this folder. Then just bookmark the page. Only one copy ever
runs: a second launch sees the first and steps aside. Details, plus how to stop it, are in the
[developer guide](docs/DEVELOPER-GUIDE.md#start-at-windows-login).

> ⚠️ **Needs internet** — for the feeds themselves, plus the thumbnails and the Google Fonts the
> page loads.
>
> ⚠️ **No login.** It only listens on `127.0.0.1`, so other PCs on the network can't reach it.
>
> ⚠️ **No background schedule.** News is fetched only while the page is open. This is on purpose:
> no scheduled task means no security-software sandbox to fight.
>
> ⚠️ **Publishers move their feeds.** If a source shows an error in *Source status* for days, its
> URL in `feeds.json` has probably changed.

To add or remove a source, edit [`feeds.json`](feeds.json) (name, url, and a section: `world`,
`business`, `markets`, `asia` or `tech` for the AI tab) and restart.

## Under the hood

| File | What it does |
|---|---|
| [`news/feeds.py`](news/feeds.py) | Loads `feeds.json`, downloads feeds in parallel with httpx, parses RSS/Atom with feedparser, strips HTML, normalises links |
| [`news/store.py`](news/store.py) | SQLite: articles (unique by link) and per-source fetch status; tab queries, search, read/saved flags, 3-day trim |
| [`news/reader.py`](news/reader.py) | Reader view: fetches one article page (public web addresses only) and extracts the story as plain paragraphs with trafilatura |
| [`news/highlights.py`](news/highlights.py) | Key sentences for the pop-up: sentences carrying the story's distinctive words (TF-IDF over all stored stories), without AI |
| [`news/server.py`](news/server.py) | FastAPI app: `/api/refresh`, `/api/articles`, `/api/articles/{id}/detail`, `/api/status`, read/save endpoints, serves the page |
| [`news/config.py`](news/config.py) | Port, paths, the 30-minute freshness window and the 3-day window |
| [`web/app.js`](web/app.js) | The page: tabs, cards, search, filters, theme. All feed text goes in via `textContent`, never `innerHTML` |
| [`web/style.css`](web/style.css) | Newspaper look, light and dark palettes |
| [`tests/`](tests/) | 55 pytest tests run against saved sample feeds and a sample article page, so they pass offline |

## Documentation

[`docs/DEVELOPER-GUIDE.md`](docs/DEVELOPER-GUIDE.md) — setup, how a refresh works step by step,
every setting, the API, the database schema, the file tree, caveats and the changelog.

<sub>Kept local by <code>.gitignore</code>: the article database <code>data/news.db</code> (created
on first run) and Python caches. The test-count badge is static and is updated by hand.</sub>
