# Diagram Flow

How News Forum runs, from Windows login to the page in your browser. File names are under
`news/` (Python server) and `web/` (the page) unless a folder is given.

## 1. Overview

What runs where. Everything except the internet sources and Telegram is on your PC.

```text
┌──────────────────────────┐        ┌──────────────────────────────────────┐
│ Your browser             │───────▶│ News Forum server                    │
│ http://127.0.0.1:8770    │  HTTP  │ python -m news · :8770               │
│                          │◀───────│ FastAPI + uvicorn (server.py)        │
│ Page: web/index.html,    │        │                                      │
│       app.js, prices.js  │        │ Endpoints:                           │
│                          │        │  /api/refresh        (get news)      │
│ Price pages load         │        │  /api/articles       (cards)         │
│ TradingView widgets HERE │        │  /api/articles/{id}/detail (pop-up)  │
└──────────────────────────┘        │  /api/feargreed  /api/fedwatch       │
                                    │  /api/etf  /api/goldth  (markets)    │
                                    └──────────────────┬───────────────────┘
                                                       │
              ┌─────────────────────────────┬──────────┴──────────────────┐
              │ SQLite                      │ HTTPS                       │ thread
              ▼                             ▼                             ▼
┌──────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────────────┐
│ data/ folder on this PC  │  │ Internet                 │  │ PriceNotifier            │
│ news.db (SQLite):        │  │ 25 RSS feeds (news)      │  │ checks clock every 30 s  │
│  • stories               │  │ Article pages (pop-up)   │  │ 6 times a day gets       │
│  • feed status/errors    │  │ alternative.me           │  │ Binance + Yahoo gold     │
│  • reader cache          │  │ Fed, NY Fed, Yahoo       │  └────────────┬─────────────┘
│ news-forum.log           │  │ SoSoValue (needs key)    │               │ HTTPS
│ telegram-sent.txt        │  │ Thai gold price site     │               ▼
│                          │  └──────────────────────────┘  ┌──────────────────────────┐
│ Read at start:           │                                │ Telegram bot             │
│  feeds.json, .env        │                                │ price message to you     │
└──────────────────────────┘                                └──────────────────────────┘
```

## 2. Startup

What happens when the app starts, at Windows login or from the `.bat` file.

```text
┌──────────────────────────┐    ┌──────────────────────────┐
│ Windows login            │    │ Double-click             │
│ Startup: News Forum.lnk  │    │ Start News Forum.bat     │
│ pythonw.exe -m news      │    │ py -3.13 -m news         │
│   --no-browser           │    │ (opens a browser tab)    │
└─────────────┬────────────┘    └─────────────┬────────────┘
              └───────────────┬───────────────┘
                              ▼
           ┌────────────────────────────────────┐
           │ news/__main__.py                   │
           │                                    │
           │ 1. No console window (pythonw)?    │
           │    → write output to               │
           │      data/news-forum.log           │
           │ 2. Port 8770 already in use?       │
           │    → open the browser, then exit   │
           │ 3. create_app(feeds.json,          │
           │               data/news.db)        │
           │ 4. Open the browser after 1 s      │
           │    (skipped with --no-browser)     │
           │ 5. Start the PriceNotifier thread  │
           │ 6. Run uvicorn on 127.0.0.1:8770   │
           └────────────────────────────────────┘
```

## 3. Getting the news (refresh)

How new stories get from the RSS feeds into the cards on the page.

```text
┌────────────────────────────────┐
│ Browser (web/app.js)           │
│ Refresh runs when:             │
│  • the page opens              │
│  • you press Refresh           │
│  • every 2 h while it's open   │
└────────────────┬───────────────┘
                 │ POST /api/refresh
                 ▼
┌────────────────────────────────┐        ┌────────────────────────────┐
│ server.py refresh()            │───────▶│ 25 RSS feeds               │
│ 1. Skip if one is running      │ HTTPS  │ (listed in feeds.json)     │
│ 2. Pick feeds last fetched     │◀───────│                            │
│    over 30 min ago             │  RSS   │ 8 downloads at a time,     │
│    (all of them if forced)     │        │ 20 s timeout each          │
│ 3. feeds.py parses each item:  │        └────────────────────────────┘
│    title, summary, image,      │
│    time, tags                  │
│ 4. Keep today + yesterday      │
└────────────────┬───────────────┘
                 │ store.py
                 ▼
┌────────────────────────────────┐
│ data/news.db                   │
│ 1. Add the new stories         │
│    (same link = skipped)       │
│ 2. Save each feed's status     │
│    and error                   │
│ 3. Delete stories older        │
│    than 2 days                 │
│    (saved ones stay)           │
└────────────────┬───────────────┘
                 │ GET /api/articles?view=…
                 ▼
┌────────────────────────────────┐
│ Browser shows the cards        │
│ for the selected tab           │
└────────────────────────────────┘
```

## 4. Reading a story (pop-up)

What happens when you click a card.

```text
┌──────────────────────────────────┐
│ Click a story card               │
│ (also marks it as read)          │
└─────────────────┬────────────────┘
                  │ GET /api/articles/{id}/detail
                  ▼
┌──────────────────────────────────┐        ┌──────────────────────────┐
│ server.py detail()               │───────▶│ The article's web page   │
│ 1. Text already in reader_cache? │ HTTPS  │ (only when not cached;   │
│    → use it                      │◀───────│  local addresses are     │
│ 2. No → reader.py downloads the  │  HTML  │  blocked)                │
│    page, trafilatura pulls out   │        └──────────────────────────┘
│    the story text, then it is    │
│    saved in reader_cache         │
│ 3. Under 400 characters or a     │
│    paywall → use the RSS text    │
│ 4. highlights.py picks up to     │
│    3 key sentences (no AI)       │
└─────────────────┬────────────────┘
                  │
                  ▼
┌──────────────────────────────────┐
│ Pop-up shows the highlights      │
│ and the full story               │
└──────────────────────────────────┘
```

## 5. Market pages

Each page under the **Markets** drop-down, the server endpoint it calls, how long the answer is reused, and where the data comes from. The Thai gold price site is ทองคำราคา.com.

```text
Markets drop-down             Server (news/*.py)                  Source on the internet
┌───────────────────────┐     ┌──────────────────────────┐        ┌─────────────────────────┐
│ Crypto / Stock Prices │────▶│ no server call:          │───────▶│ TradingView widgets     │
│ Currency to THB       │     │ the browser loads it     │        │ (USD JPY EUR GBP to     │
│                       │     │                          │        │  THB: FX_IDC feed)      │
└───────────────────────┘     └──────────────────────────┘        └─────────────────────────┘

┌───────────────────────┐     ┌──────────────────────────┐        ┌─────────────────────────┐
│ Fear & Greed          │────▶│ /api/feargreed           │───────▶│ alternative.me          │
│                       │     │ reused for 1 h           │        │                         │
└───────────────────────┘     └──────────────────────────┘        └─────────────────────────┘

┌───────────────────────┐     ┌──────────────────────────┐        ┌─────────────────────────┐
│ FedWatch              │────▶│ /api/fedwatch            │───────▶│ Fed FOMC calendar       │
│                       │     │ calendar 24 h, rate 3 h, │        │ NY Fed rate (EFFR)      │
│                       │     │ futures 10 min           │        │ Yahoo futures quotes    │
└───────────────────────┘     └──────────────────────────┘        └─────────────────────────┘

┌───────────────────────┐     ┌──────────────────────────┐        ┌─────────────────────────┐
│ BTC ETF               │────▶│ /api/etf                 │───────▶│ SoSoValue API           │
│                       │     │ reused for 30 min        │        │ needs SOSOVALUE_API_KEY │
│                       │     │                          │        │ in .env                 │
└───────────────────────┘     └──────────────────────────┘        └─────────────────────────┘

┌───────────────────────┐     ┌──────────────────────────┐        ┌─────────────────────────┐
│ Gold TH Price         │────▶│ /api/goldth              │───────▶│ Thai gold price site    │
│                       │     │ reused for 5 min,        │        │ (Gold Traders           │
│                       │     │ reads the site's HTML    │        │  Association prices)    │
└───────────────────────┘     └──────────────────────────┘        └─────────────────────────┘
```

## 6. Telegram price messages

The background thread that sends prices to your Telegram chat.

```text
┌────────────────────────────────┐
│ PriceNotifier thread           │
│ (starts with the server)       │
│ checks the clock every 30 s    │
└────────────────┬───────────────┘
                 │ at 08:30 10:30 12:30
                 │    14:30 16:30 17:30
                 ▼
┌────────────────────────────────┐        ┌──────────────────────────┐
│ TELEGRAM_BOT_TOKEN and         │───────▶│ Skip: nothing is sent    │
│ TELEGRAM_CHAT_ID in .env?      │   no   │                          │
└────────────────┬───────────────┘        └──────────────────────────┘
                 │ yes
                 ▼
┌────────────────────────────────┐        ┌──────────────────────────┐
│ Get the prices                 │───────▶│ Binance: BTC ETH ADA OP  │
│ (a failed one is shown         │ HTTPS  │ Yahoo Finance: gold      │
│  with the reason)              │◀───────│                          │
└────────────────┬───────────────┘        └──────────────────────────┘
                 │
                 ▼
┌────────────────────────────────┐        ┌──────────────────────────┐
│ Send the message               │───────▶│ Telegram bot             │
│                                │        │ → your chat              │
└────────────────┬───────────────┘        └──────────────────────────┘
                 │
                 ▼
┌────────────────────────────────┐
│ data/telegram-sent.txt         │
│ remembers the slot, so a       │
│ restart doesn't resend it      │
└────────────────────────────────┘
```
