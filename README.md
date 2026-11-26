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
  <img src="https://img.shields.io/badge/tests-104%20passing-2EA44F?logo=pytest&logoColor=white" alt="tests: 104 passing">
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
- **Only today and yesterday.** Stories from before midnight at the start of yesterday (your PC's
  time) are skipped when feeds are fetched and removed on every refresh, so the tabs stay short.
  Starred stories are never removed.
- **A broken feed doesn't break the page.** Every source is fetched separately; if one is down you
  get a one-line notice naming it and the rest of the news as usual. A dot at the top right says
  "25 sources OK" or, in red, how many are down; click it for the details.
- **Keyboard-friendly.** `←` `→` switch sections, `j` `k` move between stories, `Enter` opens one,
  `s` saves, `m` marks read, `o` opens the website, `/` searches. Press `?` for the full list.
- **Keeps itself up to date.** While the page stays open it fetches every source again every 2 hours.
  It doesn't move the list while you read: a bar says "12 new stories since this list was loaded",
  and **Show** puts them in.
- **Feeds without dates don't flood the top.** Nikkei Asia publishes no timestamps, so only its 15
  newest stories are taken, spaced out in feed order instead of all landing at "just now". Once a story
  has been cleared out it is not brought back as new, even if the feed still lists it.

## What you get

| Tab | What's in it |
|---|---|
| **Today** | Everything published in the last 24 hours, every section mixed, newest first |
| **World** | BBC World · Al Jazeera · DW · The Guardian · NPR · France 24 |
| **Business** | BBC Business · CNBC · Guardian Business |
| **Crypto & Investing** | CoinDesk · Cointelegraph · Decrypt · CNBC Markets · CNBC Investing · Guardian Money |
| **Markets ▾** (button, top right) | Opens a short menu of the market pages: BTC ETF, FedWatch, Crypto Prices, Stock Prices, Gold TH Price and Currency to THB. Picking one opens it and closes the menu; Esc or a click elsewhere closes it too. The button turns dark while a market page is open, and the menu marks which one |
| **BTC ETF** (Markets menu) | The US spot Bitcoin ETFs in one table, like CoinGlass's ETF page: fee, price, premium / discount, daily and total net inflow, net assets and value traded for each fund, largest first, with the day's totals and a bar chart of the daily net inflow (about the last 20 trading days, hover for each day) above it. CoinGlass doesn't let other sites read its table, so the figures come from SoSoValue's API, which needs a free key (see *Running it*). Flows settle a day late |
| **FedWatch** (Markets menu) | A countdown to the next FOMC rate decision (2:00 pm ET, also shown in your time) and a bar chart of the market's odds for each outcome, plus the later meeting dates. CME doesn't allow its own FedWatch tool to be embedded, so the odds are worked out on your PC with CME's published method from CBOT 30-Day Fed Funds futures (delayed quotes via Yahoo Finance). They are close to CME's figures but not identical; **Open CME FedWatch ↗** opens the real one |
| **Crypto Prices** (Markets menu) | A live price table for 14 coins (Bitcoin, Ethereum, BNB, Solana, XRP… Optimism (OP), Arbitrum (ARB)) in US dollars: price, change, change %, open, high, low. Click any row for a day chart (daily candles) in a pop-up. It's TradingView's free *Market Quotes* widget, so this tab needs internet and loads from tradingview.com. Below the table: the **Crypto Fear & Greed Index** (0 = extreme fear, 100 = extreme greed) with today's value, yesterday / last week / last month, and a history chart (30D, 90D, 1Y, All, back to 2018) with a hover readout. TradingView has no Fear & Greed symbol, so it comes from alternative.me's free API |
| **Stock Prices** (Markets menu) | The same price-only table for gold (XAU/USD, live) on top, then 15 US-listed tech stocks: Anthropic (ANT), Apple, Microsoft, Nvidia, Alphabet, Amazon, Meta, Tesla, Broadcom, TSMC, AMD, Oracle, Netflix, ASML, Intel. Free stock data from TradingView is delayed (marked with a small **D**); gold is not. Rows open the same day-chart pop-up |
| **Gold TH Price** (Markets menu) | Thai gold prices as announced by the Gold Traders Association, from [ทองคำราคา.com](https://xn--42cah7d0cxcvbbb9x.com/): the latest sell and buy-back prices for 96.5% gold bars and ornaments (baht per baht-weight), today's change, and a table of every announcement so far today with the world spot price and the baht rate. Checked every 5 minutes while the page is open |
| **Currency to THB** (Markets menu) | The US dollar, Japanese yen, euro and British pound against the Thai baht (TradingView's `FX_IDC:USDTHB`, `JPYTHB`, `EURTHB`, `GBPTHB`, interbank rates; the yen is per 1 yen, where Thai banks quote per 100) in the same price table as Crypto Prices (value, change, open, high, low, previous close), with a large USD to THB chart under it on daily candles (its toolbar switches to 1 m, 30 m or 1 h). Click a row for that currency's day chart |
| **Asia** | CNA · Nikkei Asia · Bangkok Post · The Diplomat · BBC Asia |
| **AI** | The Verge AI · The Decoder · MIT Tech Review AI · Guardian AI · Wired AI |
| **Saved** | Stories you starred, kept until you un-star them |

<p align="center">
  <img src="Pic/Screenshot%202026-11-16%20160319.png" alt="Crypto Prices view: a TradingView price table with value, change, change %, open, high, low and previous close for each coin" width="900">
</p>
<sub><b>Crypto Prices</b> (now under the <b>Markets ▾</b> menu at the top right): live prices only, no charts. Taken before OP and ARB were added to the list.</sub>

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

When a site blocks this (France 24, The Diplomat), or the item is a video or TV page,
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
> ⚠️ **No login.** It only listens on `127.0.0.1`, so other PCs on the network can't reach it. It also
> refuses requests addressed to any other host name, and changes (save, mark read, refresh) sent by
> other websites open in your browser.
>
> ⚠️ **No background schedule for news.** (The Telegram price messages are the one exception: a
> timer inside the running app, not a scheduled task.) News is fetched only while the page is open: when you open it, when
> you click Refresh, and every 2 hours while it stays open. This is on purpose: no scheduled task
> means no security-software sandbox to fight.
>
> ⚠️ **Publishers move their feeds.** If a source shows an error in *Source status* for days, its
> URL in `feeds.json` has probably changed. `py -3.13 -m pytest --live -q tests/test_feeds_live.py`
> checks every source in about 15 seconds and says what is wrong with each failing one.

**BTC ETF key (once):** sign in at <https://sosovalue.com/developer/dashboard>, click *Apply your Key*,
and paste it after `SOSOVALUE_API_KEY=` in the `.env` file in this folder (git-ignored, so the key is
never committed; the environment variable of the same name also works). Until then the BTC ETF page
shows these steps. No restart is needed.

**Telegram price messages (optional):** the app sends BTC, ETH, ADA, OP and gold (price, change, %
change) to your Telegram bot every day at 08:30, 10:30, 12:30, 14:30, 16:30 and 17:30 while it runs.
Create a bot with @BotFather and paste its token after `TELEGRAM_BOT_TOKEN=` in `.env`. Open the bot
and press **Start** (a bot can only message you after you message it). For `TELEGRAM_CHAT_ID=`, use
**your own user ID**: message @userinfobot, or take the `"chat":{"id": ...}` number from
`https://api.telegram.org/bot<token>/getUpdates`. It is the same for every bot. Not the digits before
the colon in the token: that's the bot's own ID, and Telegram can't deliver to it. Test it with
`py -3.13 -m news --send-prices`. Until both are filled in, nothing is sent. One bot can serve several of
your apps, since this one only sends. If sends fail, see the developer guide (*Telegram price
messages*).

To add or remove a source, edit [`feeds.json`](feeds.json) (name, url, and a section: `world`,
`business`, `markets`, `asia` or `tech` for the AI tab) and restart.

## Under the hood

| File | What it does |
|---|---|
| [`news/feeds.py`](news/feeds.py) | Loads `feeds.json`, downloads feeds in parallel with httpx, parses RSS/Atom with feedparser, strips HTML, normalises links |
| [`news/store.py`](news/store.py) | SQLite: articles (unique by link) and per-source fetch status; tab queries, search, read/saved flags, trim to today and yesterday |
| [`news/reader.py`](news/reader.py) | Reader view: fetches one article page (public web addresses only, checked after the name is looked up) and extracts the story as plain paragraphs with trafilatura |
| [`news/highlights.py`](news/highlights.py) | Key sentences for the pop-up: sentences carrying the story's distinctive words (TF-IDF over all stored stories), without AI |
| [`news/server.py`](news/server.py) | FastAPI app: `/api/refresh`, `/api/articles`, `/api/articles/{id}/detail`, `/api/status`, `/api/fedwatch`, `/api/feargreed`, `/api/etf`, `/api/goldth`, read/save endpoints, serves the page |
| [`news/fedwatch.py`](news/fedwatch.py) | FedWatch page: FOMC dates from the Fed's calendar, today's target range from the New York Fed, futures quotes, and the odds (CME's method), each cached for a while |
| [`news/etf.py`](news/etf.py) | BTC ETF page: the fund list, each fund's latest figures and the daily totals from SoSoValue, cached for 30 minutes |
| [`news/goldth.py`](news/goldth.py) | Gold TH Price page: reads the Gold Traders Association prices from ทองคำราคา.com's home page (no API there), cached for 5 minutes |
| [`news/feargreed.py`](news/feargreed.py) | Crypto Fear & Greed Index from alternative.me (today and the full daily history), cached for an hour |
| [`news/config.py`](news/config.py) | Port, paths, the 30-minute freshness window and the 2-day (today and yesterday) window |
| [`web/app.js`](web/app.js) | The page: tabs, cards, search, filters, theme. All feed text goes in via `textContent`, never `innerHTML` |
| [`web/fedwatch.js`](web/fedwatch.js) | The FedWatch page: countdown, odds bars, later meetings |
| [`web/etf.js`](web/etf.js) | The BTC ETF page: the totals cards and the fund table |
| [`web/goldth.js`](web/goldth.js) | The Gold TH Price page: the price cards and today's announcements |
| [`web/feargreed.js`](web/feargreed.js) | The Fear & Greed panel on Crypto Prices: today's reading, the 0-100 scale and the history chart |
| [`web/style.css`](web/style.css) | Newspaper look, light and dark palettes |
| [`tests/`](tests/) | 200 pytest tests run against saved sample feeds, a sample article page and a saved copy of the gold price page, so they pass offline. `pytest --live` adds 33 checks against the real sites: every feed, the Thai gold page, and a browser check of the price-row buttons against TradingView's real widget |

## Documentation

[`docs/DEVELOPER-GUIDE.md`](docs/DEVELOPER-GUIDE.md) — setup, how a refresh works step by step,
every setting, the API, the database schema, the file tree and caveats.
[`docs/MARKET-PAGES.md`](docs/MARKET-PAGES.md) — the Markets menu pages: BTC ETF, FedWatch (how the
odds are worked out), Crypto / Stock Prices, the Fear & Greed panel, Gold TH Price and Currency to THB.
[`docs/CHANGELOG.md`](docs/CHANGELOG.md) — what changed, and when.

<sub>Kept local by <code>.gitignore</code>: the article database <code>data/news.db</code> (created
on first run) and Python caches. The test-count badge is static and is updated by hand.</sub>
