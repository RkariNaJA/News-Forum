# News Forum — Developer Guide

> The landing page is [`../README.md`](../README.md). This guide is for whoever runs, edits or
> debugs the app: setup, internals, every setting, the API, the schema and the caveats. The market
> pages (BTC ETF, FedWatch, Crypto / Stock Prices, Fear & Greed) are in
> [`MARKET-PAGES.md`](MARKET-PAGES.md), and the history of changes in [`CHANGELOG.md`](CHANGELOG.md).

---

## 1. Setup

Requirements: Windows with the `py` launcher and Python 3.13, and internet access.

```bat
cd "News Forum"
py -3.13 -m pip install -r requirements.txt     :: exact pinned versions of fastapi, uvicorn, httpx, feedparser, trafilatura, pytest
"Start News Forum.bat"                          :: = py -3.13 -m news
```

`python -m news` ([`news/__main__.py`](../news/__main__.py)) builds the app, opens the browser
after one second and runs uvicorn on `127.0.0.1:8770`. To skip the browser, pass `--no-browser` or
set `NEWS_NO_BROWSER=1`.

If port 8770 is already in use, a launch does not start a second server. With `--no-browser` it just
exits. Without it, it opens the browser on the copy that's already running. Under `pythonw.exe`
there is no console, so output is appended to `data/news-forum.log`. Once that file passes 1 MB it
is renamed to `news-forum.log.old` and a new one starts.

### Start at Windows login

A shortcut named **`News Forum.lnk`** in the Startup folder (`Win+R` → `shell:startup`) starts the
server at login, with no window and no browser tab:

| Shortcut field | Value |
|---|---|
| Target | `…\Python313\pythonw.exe` |
| Arguments | `-m news --no-browser` |
| Start in | the `News Forum` folder (required: Python finds the `news` package from here) |

This copies the existing `Outlook Mail Watcher.lnk`. A Startup shortcut is used rather than a
Task Scheduler job, because scheduled jobs on this machine get sandboxed. Bookmark
<http://127.0.0.1:8770>.

- **Stop it.** Running `Start News Forum.bat` won't stop it. Use this PowerShell command, which
  matches News Forum only (the mail watcher is also a `pythonw.exe`):
  ```powershell
  Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | ? CommandLine -like '*-m news*' | % { Stop-Process -Id $_.ProcessId }
  ```
- **Turn off autostart.** Delete `News Forum.lnk` from `shell:startup`.
- **Something looks wrong.** Check `data/news-forum.log`.

The database `data/news.db` is created on first start. Deleting it is safe: the next page load
refetches everything (you lose read/saved marks).

## 2. How a refresh works

1. On load, [`web/app.js`](../web/app.js) calls `POST /api/refresh` (not forced). The **Refresh**
   button calls it with `force=true`. While the page stays open, an **auto-refresh** calls it (not
   forced) once `AUTO_REFRESH_MS` (2 h) has passed since the last refresh of any kind (§7).
2. [`server.py`](../news/server.py) re-reads `feeds.json` (so edits take effect without code
   changes, though a restart is the documented way) and picks the feeds whose `last_fetch` is older
   than `STALE_MINUTES`, or all of them when forced.
3. A non-blocking lock allows one refresh at a time. A second caller gets `{"busy": true}` straight
   away instead of starting a duplicate fetch.
4. [`feeds.fetch_all`](../news/feeds.py) shares one `httpx.Client` (20 s timeout, redirects on,
   plain `NewsForum/1.0` User-Agent, never a `Mozilla/...` one, which the Guardian refuses) across
   8 worker threads. Each feed returns `(articles, error)`. HTTP errors, empty feeds and even parser
   exceptions become an error for that feed only. `describe_error` makes it a short plain message
   that says what to fix: "Refused by the site (403)", "Feed moved or removed (404)", "Timed out",
   "Couldn't connect (network or firewall)", "No readable stories in the feed (its format may have
   changed)" and so on. The raw exception goes to the log. The refresh banner groups feeds by
   message, and when every feed fails it says to check the internet connection.
5. `parse_feed` turns each entry into an article:
   - **link**: must be `http(s)` with a host, or the entry is dropped. Lower-cases the host, removes
     the fragment and any query parameter starting with `utm_`, `at_`, `ito`, `cmpid`, `taid` or
     `__source`.
   - **title / summary**: HTML tags stripped, entities unescaped, whitespace collapsed. The summary
     is cut at 320 characters on a word boundary. Entries without a title are dropped.
   - **published**: `published_parsed`, else `updated_parsed`, as UTC, **capped at now** so a feed
     with future dates can't pin itself to the top. If neither exists, the entry gets
     `now − n × 20 min`, where *n* counts the undated entries so far (see §8). Only the first
     `UNDATED_MAX` (15) undated entries are kept; the rest are dropped.
   - **image**: first `http(s)` URL from `media:thumbnail`, `media:content` or an `image/*`
     enclosure.
   - **author** (up to 120 characters), **tags** (up to 6, de-duplicated without regard to case) and
     **feed_text** (see §3) for the reader pop-up.
6. Stories published before `keep_cutoff(KEEP_DAYS)` are dropped before storing, so an old story
   still listed in a feed isn't added only to be trimmed again. `store.keep_cutoff(days)` is local
   midnight at the start of the oldest day kept, in UTC: with `KEEP_DAYS = 2`, the start of yesterday
   in the PC's time zone. Calendar days, not a rolling 48 hours, so the page never shows a third day
   heading.
   `store.add_articles` does `INSERT OR IGNORE`, so a link that is already stored keeps its original
   row, including its read/saved flags and first-seen date. A link in `pruned_links` (trimmed in the
   last 14 days) is skipped, so an undated feed can't bring back a story it still lists. If the stored row has no `feed_text`
   (it was saved before the pop-up existed), its author, tags and feed text are filled in.
7. `store.record_fetch` writes the per-feed status. On error, `last_ok` keeps its previous value.
8. `store.prune(KEEP_DAYS)` deletes **unsaved** articles published before that same cutoff and
   records their links in `pruned_links`. Entries older than `FORGET_PRUNED` (14 days) are dropped.
9. The page shows any feed errors in a banner, updates the feed-health dot (§7), then reloads the
   current tab.

## 3. Reader view (the pop-up)

Clicking a card anywhere except the headline link or its buttons calls `openReader()` in
[`web/app.js`](../web/app.js). Pressing Enter on a focused card does the same.

1. The pop-up opens **instantly** with what the list already has: section, source, headline, date,
   thumbnail and blurb, plus "Loading the full story…". If the story is unread, it is marked read.
2. `GET /api/articles/{id}/detail` returns the stored article (author, tags, full feed text) and the
   reader result.
3. **Cache first.** `reader_cache` holds one row per article. A success is kept for good (until the
   daily trim removes the article). A failure is kept for `READER_RETRY` (6 h), so a blocked site
   isn't hit on every click. `?retry=true` (the pop-up's *Try again* link) refetches a cached
   failure.
4. On a cache miss, [`reader.read_article`](../news/reader.py) runs:
   - **`check_url`** allows only `http(s)` addresses that aren't local. It refuses `localhost`,
     `*.local` and any IP that is not globally routable (127.x, 10.x, 192.168.x, ::1 and so on).
     A host name is looked up first (`_resolve`), and refused if **any** address it points to is
     local, so a public name set to `127.0.0.1` (e.g. `localtest.me`) can't reach this PC. A name
     that can't be found gives "Couldn't find the site". It runs as an httpx **request hook**, so **every redirect hop** is checked, not just the first
     link.
   - **`download`** uses a browser User-Agent, a 20 s timeout and at most 5 redirects, and streams
     the page with a 5 MB cap. A 403 is retried once with the plain `NewsForum/1.0` User-Agent (the
     Guardian refuses a browser one from a non-browser client). The status codes
     401/402/403/405/429/451 become "The site refused the request (n)". A response that isn't HTML is refused.
   - **`extract`** calls `trafilatura.bare_extraction` with precision on, and without comments,
     tables or images. That gives the text plus the page's `author`, `date` and `image`. Then:
     - Before the story starts, it skips the headline, the byline and any line under 30 characters
       ("Published", "Share").
     - It strips trafilatura's `- ` list markers.
     - It stops at 80 paragraphs or 40,000 characters.
   - **Rejected as "no story"**: under 400 characters (paywall teaser, video page), or more than
     60 % list items (an episode list or index page).
5. **Plain text only.** Paragraphs go into `<p>` elements via `textContent`, and the publisher's
   HTML never reaches the page. The image is taken only if it is `http(s)`.
6. **On failure**, the pop-up shows the reason and the feed's own text. That's `feed_text`: the
   richer of the feed's `content:encoded` and its summary, split into paragraphs, up to 6,000
   characters. The card's 320-character blurb is used when `feed_text` is empty.
7. A request token stops a slow response from overwriting a story opened after it. Esc, ✕ or a
   click on the backdrop closes the pop-up.

### Key-sentence highlights

[`news/highlights.py`](../news/highlights.py) picks the story's most important sentences locally, without AI.

1. **Document frequencies.** `Corpus` counts, for each word stem, how many stored stories contain it. A
   story here means its title, blurb and feed text. The server keeps one `Corpus` and rebuilds it only
   when `(row count, max id)` changes, that is, after a refresh adds stories or the trim removes some.
2. **Word weights.** Text is lowercased, and stopwords and news filler are skipped ("said", weekdays,
   months, "million"). `stem()` groups possessive and plural forms (`gorillas`, `jojo's` and `companies`
   become `gorilla`, `jojo` and `company`). Each stem weighs `count in this story × idf`, × 1.6 if it's in
   the headline. Words from the source's or the author's name weigh nothing.
3. **Sentences.** `split_sentences()` cuts each paragraph at `.`, `!` or `?` followed by a capital, digit
   or quote, but not after abbreviations (`Mr.`, `U.S.`, `Inc.`) or single initials (`Donald J. Trump`).
   Every sentence is an exact substring of its paragraph. Sentences under 8 or over 60 words, and one
   that just repeats the headline, are skipped.
4. **Scoring.** A sentence scores the sum of its distinct stems' weights ÷ √(number of content words), so
   long sentences don't win just by being long. The story's first sentence gets × 1.2.
5. **Picking.** One sentence per 8 candidates, rounded up, at most `MAX_SENTENCES` (3). Best first, at most
   one per paragraph, and a sentence sharing 60 % (`SAME_POINT`) of its words with one already picked is
   skipped (CoinDesk restates its lead as a bullet). The result comes back in reading order.

The API returns them as `highlights`. The page ([`web/app.js`](../web/app.js)) finds each sentence in its
paragraph with `indexOf` and wraps it in a `<mark class="key">` next to plain text nodes, never
`innerHTML`. The **Highlights** switch is stored in `localStorage` as `highlights`.

The API also drops a first paragraph that just repeats the headline. The comparison uses letters and
digits only, so curly and straight quotes count as the same. This also applies to results cached
before the check existed.

Coverage measured on 54 recent stories (3 per source) on 2026-11-16: **39 full text**.

| Result | Sources |
|---|---|
| ✅ Full text (3/3) | BBC World, BBC Asia, BBC Science, Bangkok Post, CNA, CNBC, DW, NPR, Nikkei Asia, The Guardian, The Verge |
| ⚠️ Mostly | Al Jazeera (2/3), BBC Tech (2/3: one item was an iPlayer TV episode), Guardian Business (2/3: one reader call-out form) |
| ❌ Videos | BBC Business (the 3 newest were `/news/videos/` pages; its articles extract fine) |
| ❌ Site refuses | France 24 (403), The Diplomat (403), Ars Technica (405; its feed carries ~950 characters, which the fallback shows) |

The Crypto & Investing feeds were chosen with the same check: CoinDesk, Cointelegraph, Decrypt, CNBC Markets, CNBC
Investing and Guardian Money each gave 3 of 3 full stories. Rejected because their article pages refuse:
The Block (403), Bitcoin Magazine (403), MarketWatch (401), Investing.com (403) and Seeking Alpha (403).
Yahoo Finance's feed URL returned 404.

On 2026-11-20 the Tech & Science feeds above (BBC Tech, Ars Technica, The Verge, BBC Science) were
replaced by AI-only feeds, measured the same way (3 newest stories each, with the app's own fetcher and
reader):

| Result | AI sources |
|---|---|
| ✅ In use | Wired AI (3/3), The Verge AI (3/3, short pieces), MIT Tech Review AI (3/3; one was a 500-character "Research Reports" page), The Decoder (3/3, 4,500–5,600 characters), Guardian AI (2/3: one live blog, rejected as a list page) |
| ✅ Work, not used | TechCrunch AI (3/3, overlaps The Verge), VentureBeat AI (3/3, enterprise opinion), Hugging Face Blog (3/3, very technical) |
| ❌ Dropped | Ars Technica AI (0/3: article pages refuse with 405, feed text only 600–1,000 characters); replaced by The Decoder the same day |
| ❌ Not used | The Register AI (0/3, pages read as link lists), AI News (feed unreadable) |

A quick `curl` check had shown TechCrunch (403) and VentureBeat (429) refusing; the app's own client
reads both fine, so check feeds with `fetch_all`, not `curl`.

## 4. Settings

All in [`news/config.py`](../news/config.py) unless noted.

| Setting | Value | Effect |
|---|---|---|
| `HOST` / `PORT` | `127.0.0.1` / `8770` | Where uvicorn listens. Loopback only, so the LAN cannot reach it |
| `ALLOWED_HOSTS` | `127.0.0.1`, `localhost` | Host names the server answers; any other `Host` header gets 400 (blocks DNS rebinding) |
| `STALE_MINUTES` | `30` | A feed is refetched on page open when its last fetch is older than this |
| `KEEP_DAYS` | `2` | Calendar days kept, in the PC's time zone: 2 = today and yesterday. Older stories are skipped when fetched, and unsaved ones are deleted on every refresh |
| `CATEGORIES` | world, business, markets, asia, tech | Allowed `category` values in `feeds.json`; also the tab names. `markets` is shown as *Crypto & Investing* and `tech` as *AI* |
| `FEEDS_PATH` / `DB_PATH` / `WEB_DIR` | `feeds.json`, `data/news.db`, `web/` | Relative to the project folder |
| `TTL` / `RETRY_AFTER` (etf.py) | `1800 s` / `120 s` | How long SoSoValue's answer is reused, and how long to wait after a failure. One refresh is 2 calls plus one per fund; SoSoValue allows 20 a minute (`MAX_FUNDS` = 17) |
| `SOSOVALUE_API_KEY` (`.env`) | none | SoSoValue API key for the BTC ETF page: the environment variable wins, else the `SOSOVALUE_API_KEY=` line of `.env` in the project folder (git-ignored; `read_dotenv` in etf.py, no extra package). Read on every request, so adding it needs no restart |
| `TIMEOUT` (feeds.py) | `20.0` s | Per-request HTTP timeout |
| `SUMMARY_MAX` (feeds.py) | `320` | Blurb length before truncation |
| `UNDATED_STEP` (feeds.py) | `20 min` | Spacing for entries with no date |
| `UNDATED_MAX` (feeds.py) | `15` | Most undated entries taken from one feed per fetch |
| `FORGET_PRUNED` (store.py) | `14 days` | How long a trimmed link is kept from being stored again |
| `LIST_LIMIT` (store.py) | `400` | Most articles returned for one tab |
| `FEED_TEXT_MAX` (feeds.py) | `6000` | Feed text kept for the pop-up fallback |
| `READER_RETRY` (store.py) | `6 h` | How long a failed article extraction is cached before it is retried |
| `PAGE_TIMEOUT` / `MAX_PAGE_BYTES` (reader.py) | `20 s` / `5 MB` | Article page download limits |
| `MIN_TEXT_CHARS` / `MAX_LIST_SHARE` (reader.py) | `400` / `0.6` | Below this, or more list than prose, the page counts as "no story" |
| `MAX_PARAGRAPHS` / `MAX_TEXT_CHARS` (reader.py) | `80` / `40000` | Most text shown in the pop-up |
| `MAX_SENTENCES` / `SENTENCES_PER_PICK` (highlights.py) | `3` / `8` | How many sentences are highlighted: one per 8, at most 3 |

### `feeds.json`

```json
{"name": "BBC World", "category": "world", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"}
```

`load_feeds` silently skips an entry with a missing name, a category not in `CATEGORIES`, or a URL
that isn't `http(s)`. Names must be unique: they key the status table, and a test enforces it.

## 5. API

| Method & path | Body / query | Returns |
|---|---|---|
| `POST /api/refresh` | `?force=true\|false` | `{busy, fetched, new, pruned, errors: {name: message}}` |
| `GET /api/articles` | `?view=today\|world\|business\|markets\|asia\|tech\|saved&q=` (q ≤ 100 chars) | `{view, articles: [...], counts: {tab: unread}}`; an unknown view gives 400 |
| `POST /api/articles/{id}/read` | `{"value": bool}` | `{ok, counts}`, or 404 for an unknown id |
| `POST /api/articles/{id}/saved` | `{"value": bool}` | `{ok, counts}`, or 404 for an unknown id |
| `GET /api/articles/{id}/detail` | `?retry=true` refetches a cached failure | `{article: {...all fields, tags: [...]}, feed_text: [paragraphs], reader: {ok: true, paragraphs, author, date, image} or {ok: false, error}, highlights: [sentences]}`; 404 for an unknown id |
| `POST /api/articles/read-all` | `{"ids": [int, ...]}` (≤ 1000) | `{updated, counts}` |
| `GET /api/counts` | | `{tab: unread}`: the tab badges on their own, without the stories |
| `GET /api/fedwatch` | | `{next: {date, label, sep, decision}, upcoming: [...], target: {low, high, effr, as_of}, odds: {meeting, outcomes: [{move_bp, low, high, prob}], rate_before, rate_after, anchor, contracts: [{symbol, price, time}]}, errors: {name: message}, cme_url}`; a part that failed is `null` and named in `errors` (calendar, rate or futures) |
| `GET /api/etf` | | `{funds: [{ticker, name, exchange, date, fee, price, prem_dsc, net_inflow, cum_inflow, net_assets, value_traded}], totals: {date, net_inflow, value_traded, net_assets, cum_inflow}, history: [[date, net_inflow], ...], missing: [ticker], as_of, error, needs_key, key_env, env_file, key_url, source_url}`; fee and `prem_dsc` are ratios (0.0025 = 0.25 %), money in US dollars. With no key, `needs_key` is true and nothing is fetched |
| `GET /api/feargreed` | | `{current: {date, value, label}, history: [[date, value], ...] oldest first, next_update, error, source_url}`; with nothing cached and alternative.me down, `current` is `null` and `error` says why |
| `GET /api/status` | | `{feeds: [{name, url, category, last_fetch, last_ok, error, last_count}]}` |
| `GET /` and `/static/*` | | The page and its assets, sent with `Cache-Control: no-cache` so the browser re-checks them (ETag) on every load |

**Same-origin writes.** A `POST` whose `Origin` header doesn't match its `Host` gets 403, so another
site open in the browser can't save, mark or refresh. Requests with no `Origin` (curl, scripts) pass.

`today` means published in the last 24 hours, across all sections. A tab with no unread stories is left out of `counts`. `counts.saved` is the total
saved, not unread. Search is a case-insensitive `LIKE` on title and summary, with `%`, `_` and `\`
escaped so they match literally.

## 6. Database schema

```sql
articles(id PK, link UNIQUE, title, summary, source, category, image,
         published TEXT, fetched TEXT, is_read 0/1, saved 0/1,
         author, tags (JSON list), feed_text)     -- last 3 added for the pop-up
  -- indexes: (published), (category, published)
feed_status(name PK, url, category, last_fetch, last_ok, error, last_count)
reader_cache(article_id PK, fetched, ok 0/1, data (JSON), error)
pruned_links(link PK, pruned)                     -- trimmed links, kept 14 days
```

**Migration:** on start, `Store` adds any missing `author` / `tags` / `feed_text` columns with
`ALTER TABLE`, so a database from the first release keeps working and keeps its read/saved marks.
`prune` also removes `reader_cache` rows whose article is gone.

Timestamps are ISO-8601 UTC strings, so string order equals time order. Each call opens its own
connection; writes go through a `threading.Lock` because uvicorn handles requests on a thread pool.

## 7. Front end

Plain HTML/CSS/JS, no build step, as six classic scripts that share globals, loaded in this order:
[`web/etf.js`](../web/etf.js) (the BTC ETF page),
[`web/fedwatch.js`](../web/fedwatch.js) (the FedWatch page),
[`web/feargreed.js`](../web/feargreed.js) (the Fear & Greed panel),
[`web/prices.js`](../web/prices.js) (price pages and the chart pop-up),
[`web/app.js`](../web/app.js) (everything else) and [`web/keys.js`](../web/keys.js) (keyboard shortcuts).
`index.html` loads them, and `style.css`, with a version query (`?v=16`). **Raise that number whenever you
change a JS or CSS file**, so a browser holding an older copy fetches the new one.

[`web/app.js`](../web/app.js):

- Inserts feed text only through `textContent`, and only gives `href`/`src` to URLs that parse as
  `http(s)` (`safeUrl`). Links open with `rel="noopener noreferrer"`, and the page sends no
  referrer when loading thumbnails.
- Saves per-browser preferences in `localStorage`: `view` (last tab), `theme`, `hideRead`, `highlights`,
  `lastRefresh` (drives the "Updated … ago" label). All reads and writes are wrapped, so a blocked
  storage still renders the page.
- Updates read/saved state optimistically, then shows the tab counts that come back with the reply
  (no second request).
- **Auto-refresh.** A one-minute timer (the same one that updates "Updated … ago") calls
  `autoRefreshIfDue()`, and so does the tab becoming visible again. Once `AUTO_REFRESH_MS` (2 h) has
  passed since the last refresh, it calls `refresh(false, auto = true)`. Checking every minute instead
  of one 2-hour timer means it catches up after the PC sleeps, and any refresh (on open, the button,
  `r`) restarts the 2 hours. The time is kept in memory (`lastRefreshAt`), not `localStorage`, so
  blocked storage can't make it fire every minute; `refreshing` stops overlapping refreshes. An auto
  refresh updates the tab counts, the health dot and the feed alert but **doesn't redraw the list**:
  if the server reports new stories, `#new-bar` says "n new stories since this list was loaded" (added
  up across auto refreshes) and **Show** reloads the list. Any `load()` (Show, a tab change, a manual
  refresh) hides the bar and resets the count. The bar isn't shown on the price pages. Checked in a
  browser on 2026-11-20 with Playwright's fake clock: no call at 1 h 30, one at 2 h 01, the list left
  as it was until Show, the next call 2 h after that.
- Shows day headings ("Today", "Yesterday", …) on every tab except **Today**.
- Cards are focusable (`tabindex=0`, `data-id` = article id) and open the reader on click or Enter (§3).
  The reader is a native `<dialog>`, full-screen below 560 px.
- The selected tab (`aria-selected="true"`) gets a tinted background, bold accent text, a 3 px underline
  and a filled count badge.
- **Feed health.** `checkHealth()` reads `GET /api/status` on load and after every refresh. A feed is a
  problem (`feedProblem`) when its last fetch had an error, or worked but returned no stories. The
  masthead dot (`#health`) reads "● 25 sources OK" in green, or "● n sources down" in red, and opens
  *Source status*, which lists problem feeds first, tinted, with when they last worked. The tagline's
  source count comes from the same call.
- **Market pages** (the **Markets ▾** menu at the top right: BTC ETF, FedWatch, Crypto Prices with the
  Fear & Greed panel, Stock Prices, and the day-chart pop-up) have their own file:
  [`MARKET-PAGES.md`](MARKET-PAGES.md).
- **Keyboard shortcuts** (`keys.js`, help box on `?` or the footer link): `←`/`→` and `1`–`7` switch
  tabs, `j`/`k` or `↓`/`↑` move between cards, `o` opens the story's site, `s` saves, `m` toggles
  read, `/` focuses search, `r` forces a refresh. In the reader, `j`/`k` go to the next or previous
  story (with *Hide read* on, `j` skips read stories), `s` saves, `o` opens the site. Keys are ignored
  while typing in a field, with Ctrl/Alt/Meta held, and while another dialog is open. After `s` or `m`
  re-renders the list, focus goes back to the same card, or to the one now in its place.

[`web/style.css`](../web/style.css) defines colour tokens on `:root`, with a dark set applied by the
◐ toggle or by the OS setting. Fonts are Newsreader and Inter from Google Fonts, falling back to
Georgia and Segoe UI when offline.

## 8. Caveats

- **Undated feeds.** Nikkei Asia sends no dates. Only its 15 newest entries are taken, and its
  first fetch is spread 20 minutes apart in feed order. After that, only new links are inserted and they get the fetch time, which is close to
  reality if you open the page a few times a day.
- **Fetching only happens while you use it.** The server runs from login, but it fetches only when
  the page is opened or refreshed, or every 2 hours while a page stays open (the timer is in the page,
  not the server). After a long break the first load takes a few seconds. Two open tabs each
  auto-refresh, but the server's refresh lock and `STALE_MINUTES` stop the second from fetching
  again.
- **Dead feeds.** NHK World's English RSS address returned 404 when this was built, so it is not in
  the list. The masthead dot turns red when a feed fails; click it (or *Source status* in the footer)
  to see which.
- **Thumbnails and fonts are loaded from the publishers and Google**, so those requests do leave
  your PC (the feed fetches do too, obviously). The price pages load TradingView's widget script and
  iframe, and the chart pop-up loads a second one, only while they are open.
- **The pop-up fetches the publisher's page from your PC**, the same as opening the article.
  Publishers change their layouts, so extraction can start missing on a site and then fall back to
  the feed text. If one source keeps failing, check it with *Try again*, then look at
  `reader.extract`.
- **Images in the pop-up** come from the page's own share image (`og:image`). Some, such as The
  Guardian's, have the publisher's logo printed on them.
- **No authentication.** That's fine on loopback, with the host-name and same-origin checks (§5). Don't change `HOST` to `0.0.0.0` without adding
  some.
- Caveats of the market pages (SoSoValue, FedWatch, TradingView's layout) are in
  [`MARKET-PAGES.md`](MARKET-PAGES.md#6-caveats).
- The test-count badge in the README is static.

## 9. Tests

```bat
py -3.13 -m pytest -q
```

104 tests, all offline (plus 5 live ones, below, that a plain run skips):

- [`test_feeds.py`](../tests/test_feeds.py): RSS and Atom parsing, HTML cleanup, link
  normalisation and unsafe schemes, future and missing dates, truncation, `feeds.json` validation
  (including the real file).
- [`test_store.py`](../tests/test_store.py): de-duplication, tab queries, wildcard-safe search,
  flags and counts, prune keeps saved articles, trimmed links aren't stored again (for 14 days),
  `last_ok` survives an error.
- [`test_server.py`](../tests/test_server.py): runs the API with a fake fetcher. Covers refresh and
  errors, skipping fresh feeds, flags, input validation, status, serving the page, and the
  `no-cache` header on the page and its assets (but not on the API), other host names refused, and
  writes from other sites refused, and read/save replies carrying fresh tab counts.
- [`test_highlights.py`](../tests/test_highlights.py): topic sentences beating filler, exact text in
  reading order, short and empty stories, the headline and restated points not picked, sentence
  splitting around abbreviations and quotes, source-name words ignored, plural grouping.
- [`test_reader.py`](../tests/test_reader.py): story extraction from a sample article page (no
  menus, cookie banner or footer), dropping leading labels and list markers, paywall and list-page
  rejection, local and odd URLs refused (including a redirect to `127.0.0.1`), host names that point
  at local addresses refused (lookups faked, so the tests stay offline), and refusals turned into
  readable errors.
- Pop-up additions to the other test files: `author`, `tags` and `feed_text` parsing; backfill;
  migrating a first-release database; reader cache (kept on success, retried after a failure);
  `/detail` fetching once and then using the cache; `retry=true`; a crashing extractor.
- [`test_fedwatch.py`](../tests/test_fedwatch.py): calendar parsing (notation votes, two-month
  meetings, `*`, 2:00 pm ET in winter and summer), contract symbols, the odds split, each way of
  anchoring the rates (month before, month after, last-day meeting, today's rate), caching, skipping
  past meetings, a failing source, and falling back to the last good answer. All sources are faked.
- [`test_etf.py`](../tests/test_etf.py): the table built from faked SoSoValue answers (largest fund
  first, string numbers, dates as text or millisecond timestamps, a fund with no figures), a refused key,
  the rate limit (stopping at it, without asking for the rest), a refresh with most funds missing
  failing while the last complete table stays, a changed fund list, the `{code, data}` wrapper, the key from `.env` or the environment,
  no fetch without a key, the 30-minute cache, the wait after a failure, and keeping the last answer.
- [`test_feargreed.py`](../tests/test_feargreed.py): history ordered oldest first, today's value and
  label, the next-update time, changed or empty data rejected, the hour-long cache, and the last answer
  kept when a later fetch fails.
- [`test_main.py`](../tests/test_main.py): detecting a server already on the port, a second launch
  not starting another server, and windowless output going to the log file.

Sample feeds and a sample article page (`article.html`) are in `tests/fixtures/`.

### Live tests (`--live`)

```bat
py -3.13 -m pip install playwright          :: once; test-only, not in requirements.txt
py -3.13 -m pytest --live -q tests/test_price_rows_live.py
```

[`test_price_rows_live.py`](../tests/test_price_rows_live.py) needs internet (TradingView) and drives
Microsoft Edge through Playwright, falling back to Playwright's own Chromium if Edge won't start. It
serves the real page on a free port with an empty feed list and a throwaway database, so it never
touches `data/news.db` or the running app. Without `--live` the 5 tests show as skipped
(`conftest.py` adds the switch and the `live` marker).

- **Every row button on its own row**: Crypto Prices and Stock Prices, at 1280 px and 390 px wide. For
  each button it reads which widget row is under the button's top, middle and bottom, and fails with
  lines like `Gold (XAU/USD): at y=88 the widget shows 'Anthropic'` and a pointer to `QUOTE_ROW`.
  Checked to fail by moving `QUOTE_ROW.top` from 52 to 70 px.
- **A click opens the day chart, not a tab**: the right title, the chart iframe, no new browser tab,
  and Esc closes and empties the pop-up.

Run it after TradingView looks different, or now and then. The feed-health dot and keyboard shortcuts
have no automated tests; they were checked by hand in a browser on 2026-11-20.

## 10. File tree

```
News Forum/
├── README.md                ← landing page
├── docs/
│   ├── DEVELOPER-GUIDE.md   ← this file
│   ├── MARKET-PAGES.md      ← the Markets menu pages
│   └── CHANGELOG.md         ← history of changes
├── Start News Forum.bat     ← launcher (py -3.13 -m news)
├── feeds.json               ← source list
├── requirements.txt
├── .gitignore               ← .env, data/*.db, data/*.log, caches
├── news/
│   ├── __main__.py          ← entry point: --no-browser, single instance, log file, uvicorn
│   ├── config.py            ← settings
│   ├── etf.py               ← BTC ETF page: US spot Bitcoin ETFs (SoSoValue), cached
│   ├── feargreed.py         ← Crypto Fear & Greed Index (alternative.me), cached
│   ├── fedwatch.py          ← FedWatch page: FOMC calendar, target range, futures, odds
│   ├── feeds.py             ← fetch + parse
│   ├── highlights.py        ← key sentences for the pop-up highlights (TF-IDF, no AI)
│   ├── reader.py            ← reader view: safe page download + story extraction
│   ├── store.py             ← SQLite (articles, feed status, reader cache)
│   └── server.py            ← FastAPI routes
├── web/                     ← index.html, style.css, etf.js, fedwatch.js, feargreed.js, prices.js, app.js, keys.js
├── Pic/                     ← README screenshots
├── data/                    ← news.db + news-forum.log, created on first run (git-ignored)
└── tests/                   ← conftest.py, test_*.py, fixtures/
```
