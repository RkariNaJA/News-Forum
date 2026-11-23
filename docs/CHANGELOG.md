# News Forum — Changelog

> Newest last. The [developer guide](DEVELOPER-GUIDE.md) describes the app as it is now.

- **2026-11-16**: First version. 18 feeds across 4 sections. Tabs, read/save, search, source
  filter, source status, dark mode. Undated feeds get spread timestamps. README and developer guide
  added.
- **2026-11-16**: Starts at Windows login from a Startup shortcut (`pythonw`, `--no-browser`). Only
  one copy runs at a time, and windowless output goes to `data/news-forum.log`.
- **2026-11-16**: Reader view. Clicking a card opens a pop-up with the full story, extracted with
  trafilatura and cached, falling back to the feed text. Feeds now keep author, tags and full feed
  text, and older databases are migrated automatically.
- **2026-11-16**: New **Crypto & Investing** tab (`markets` category, amber tag) with 6 feeds: CoinDesk,
  Cointelegraph, Decrypt, CNBC Markets, CNBC Investing and Guardian Money. 24 feeds in total. A story already
  stored from another feed (e.g. the main CNBC feed) keeps its first tab.
- **2026-11-16**: Key-word highlights in the pop-up. Distinctive words and names (TF-IDF, no AI) get a
  marker stroke, and money and percent figures are bold and underlined. There's a *Key words* row and
  a **Highlights** switch. A headline repeated as the first paragraph is now removed.
- **2026-11-16**: Highlights changed from key words to key sentences, at the user's request: 1 to 3 of
  the story's most important sentences get a marker. `news/keywords.py` became `news/highlights.py`;
  the word marks, money/percent marks and the *Key words* row are gone.
- **2026-11-16**: New **Crypto Prices** tab: TradingView's *Market Quotes* widget, prices only (no
  chart), 12 coins in USD. Then moved, at the user's request, from the tab bar to a **Crypto Prices**
  button at the top right, next to Refresh. Optimism (`BINANCE:OPUSDT`) and Arbitrum (`BINANCE:ARBUSDT`) added: 14 coins.
- **2026-11-16**: New **Stock Prices** button next to Crypto Prices: the same price-only widget for 14
  US-listed tech stocks. Both pages now share one `PRICE_PAGES` table in `app.js`. Gold
  (`OANDA:XAUUSD`, live, not delayed) added as the first row of Stock Prices.
- **2026-11-16**: News kept for 4 days instead of 30, at the user's request ("too much"). `KEEP_DAYS`
  is 4, and the refresh skips stories older than that before storing. The first run removed 172
  stories (749 → 577). Then lowered to 3 days, also at the user's request.
- **2026-11-20**: The **Tech & Science** tab became **AI**: its 4 feeds were replaced by 5 AI-only
  feeds (The Verge AI, Ars Technica AI, MIT Tech Review AI, Guardian AI, Wired AI), 25 feeds in total.
  The category key stays `tech`. Unsaved stories from the old feeds were deleted from the database.
- **2026-11-20**: The selected tab is highlighted (tinted background, bold accent text, thicker
  underline). The page and its assets are served with `Cache-Control: no-cache`, and `index.html`
  versions its CSS/JS links, so changes show on a normal refresh.
- **2026-11-20**: Feed-health dot in the masthead, and *Source status* lists problem feeds first. The
  tagline's source count is now live. Keyboard shortcuts (`keys.js`, `?` for help). Anthropic
  (`NASDAQ:ANT`) added to Stock Prices. The price code moved from `app.js` to `prices.js` to keep
  files under 500 lines.
- **2026-11-20**: Clicking a row on Crypto Prices or Stock Prices opens a day chart (daily candles,
  TradingView's Advanced Chart widget) in a pop-up instead of a new TradingView tab.
- **2026-11-20**: Full-text check of the AI feeds ([guide §3](DEVELOPER-GUIDE.md#3-reader-view-the-pop-up)). Ars Technica AI (0/3, site refuses the reader)
  replaced by The Decoder (3/3). Still 25 feeds.
- **2026-11-20**: `pytest --live` runs a browser check of the price-row buttons against TradingView's
  real widget (`tests/test_price_rows_live.py`, Playwright + Edge). A plain `pytest` skips it.
- **2026-11-20**: News kept for **today and yesterday** only, at the user's request ("too much").
  `KEEP_DAYS` is now 2 and counts calendar days from local midnight (`store.keep_cutoff`) instead of a
  rolling window, so there's no part-day third heading. The first run removed 507 stories (1,147 → 650
  stored; unread World 484 → 287). The window test now uses stories one minute either side of the
  cutoff, so it can't fail around midnight.
- **2026-11-20**: Auto-refresh every 2 hours while the page is open, at the user's request. New stories
  wait behind a "n new stories · Show" bar instead of redrawing the list mid-read.
- **2026-11-23**: Undated feeds capped at their 15 newest entries (Nikkei Asia had 50 of 239 stored
  stories). Trimmed links are remembered for 14 days in `pruned_links`, so a feed that still lists them
  can't bring them back as new. The server now answers only to `127.0.0.1` / `localhost` and refuses
  `POST`s from other sites (`Origin` ≠ `Host`). 64 tests.
- **2026-11-23**: Save / Mark read replies now carry the tab counts, and the badges use the new
  `GET /api/counts`, so a click no longer reloads up to 400 stories. The reader looks up a host name
  before fetching and refuses it if any address it points to is local (a public name set to
  `127.0.0.1` used to get through). Leftover "3-day" wording fixed. 71 tests.
- **2026-11-23**: **FedWatch** button, left of Crypto Prices, at the user's request: a countdown to the
  next FOMC decision and a bar chart of the futures-implied odds, with the later meetings. CME's tool
  can't be embedded, so `news/fedwatch.py` applies CME's method to CBOT 30-Day Fed Funds futures, with
  the Fed's calendar and the New York Fed's target range; `GET /api/fedwatch`; `tzdata` added to
  `requirements.txt`. The live chart-pop-up test now waits for the dialog's `close` event (it fires on a
  later task): that was the occasional live-test failure noted on 2026-11-20 (it failed 2 of 5 runs
  before the fix, passed 10 of 10 after). Page files now `?v=7`. 83 tests.
- **2026-11-23**: **Crypto Fear & Greed Index** under the Crypto Prices table, at the user's request:
  today's value on a 0-100 scale, yesterday / last week / last month, and a history chart (30D to All,
  from Feb 2018) with a hover readout. TradingView has no such symbol, so `news/feargreed.py` reads
  alternative.me's free API; `GET /api/feargreed`. New `--greed-strong` colour, checked with the
  palette validator for colour-blind separation. Page files now `?v=8`. 91 tests.
- **2026-11-23**: **BTC ETF** button, left of FedWatch, at the user's request: the US spot Bitcoin ETFs
  in a table like CoinGlass's (fee, price, premium / discount, daily and total net inflow, net assets,
  value traded) with the day's totals. CoinGlass's table comes from a private API, so at the user's
  choice `news/etf.py` reads SoSoValue's API with a free key (`SOSOVALUE_API_KEY` in `.env`,
  git-ignored, or the environment); `GET /api/etf`. `selectTab` now shows any page's own section generically.
  Checked in the browser against faked data only, as no key was set up yet. Page files `?v=10`. 101 tests.
- **2026-11-23**: the four market page buttons (BTC ETF, FedWatch, Crypto Prices, Stock Prices) left the
  masthead, which had grown crowded (three rows on a phone), into one **Markets ▾** drop-down at the top
  right, at the user's request (hidden until wanted). A fold-out group at the end of the tab row was tried
  first; the user preferred the top right. The SoSoValue key now lives in `.env` (`SOSOVALUE_API_KEY=`,
  git-ignored) instead of `data/sosovalue.key`. Page files `?v=12`.
- **2026-11-23**: BTC ETF checked on real data (fee units confirmed). An empty column is hidden;
  a refresh stops at the first refusal (`EtfAbort`) and one with most funds missing counts as a failure,
  so the last complete table stays. Page files `?v=13`. 104 tests.
- **2026-11-23**: The developer guide (614 lines, over the project's 500-line rule) split in three:
  the guide, [`MARKET-PAGES.md`](MARKET-PAGES.md) (the Markets menu pages, their caveats and the
  FedWatch method) and this changelog. Two bullets that had ended up under the FedWatch heading (the
  day-chart pop-up and keyboard shortcuts) went back where they belong. BTC ETF gets a **daily net
  inflow** bar chart from the daily totals it already downloaded. Page files `?v=15`.
