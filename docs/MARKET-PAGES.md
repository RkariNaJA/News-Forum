# News Forum — Market Pages

> The six pages behind the **Markets ▾** menu at the top right: BTC ETF, FedWatch, Crypto Prices (with
> the Fear & Greed panel), Stock Prices, Gold TH Price and Currency to THB. Everything else (setup, the news side, settings, the API,
> tests) is in the [developer guide](DEVELOPER-GUIDE.md); past changes are in the
> [changelog](CHANGELOG.md).

All six are entries in `PRICE_PAGES` (`web/prices.js`) and use `view` values the API doesn't have, so
they hide the story list and toolbar. A page with its own `section` and `mount` (BTC ETF, FedWatch, Gold TH Price) draws
itself; the others embed TradingView's widget in `#prices`.

---

## 1. The Markets menu

- **Markets** (`#markets-toggle`, top right, left of Refresh) opens a drop-down (`#market-tabs`,
  `.market-pop`, absolutely placed under the button, right-aligned) with the six market pages: BTC ETF,
  FedWatch, Crypto Prices, Stock Prices, Gold TH Price, Currency to THB. `setMarketsOpen` in `app.js` shows or hides it and sets
  `aria-expanded`; picking an item calls `selectTab` and closes it, as do Esc (focus goes back to the
  button) and any click outside `.markets-menu`. `selectTab` sets `aria-pressed` on the item of the open
  page and the class `on` on the button, which turns it dark like a pressed `.btn`. The items carry
  `data-view` but sit outside `.tabs`, so `←`/`→` and the number keys still cycle the news tabs only.

## 2. Crypto Prices, Stock Prices and Currency to THB

- **Crypto Prices** and **Stock Prices** (`view = "prices"` / `"stocks"`, page-only; the API has no such
  views). Each is an item (`#prices-btn`, `#stocks-btn`) in the **Markets** drop-down (§1). Both hide the list and toolbar and embed TradingView's free
  *Market Quotes* widget (`s3.tradingview.com/external-embedding/embed-widget-market-quotes.js`), which
  renders an iframe that updates itself. TradingView has no public price API, so the widget is the
  supported way. Each page is an entry in `PRICE_PAGES` in `prices.js`: its group name, note text
  and `symbols` as `EXCHANGE:TICKER` names (crypto: Binance USDT pairs; stocks: `NASDAQ:`/`NYSE:`, with spot
  gold `OANDA:XAUUSD` first, then Anthropic `NASDAQ:ANT`, listed 2026-11-19).
- **Currency to THB** (`view = "currency"`, `#currency-btn`, last in the Markets menu) is the same kind of
  page with four rows: `FX_IDC:USDTHB`, `JPYTHB`, `EURTHB` and `GBPTHB` (TradingView's default feed for
  these pairs, the interbank rate; `OANDA:USDTHB` also exists). The yen is per 1 yen (about 0.2 baht);
  Thai banks quote per 100, which the page's note says. The entry also has `chart: "FX_IDC:USDTHB"`, so
  `mountPrices` puts the USD to THB *Advanced Chart*
  (daily candles, built by `chartWidget()`, the same function the day-chart pop-up uses) in `#prices-chart`
  under the table. Other pages hide and empty `#prices-chart`. The FX change is since the previous daily
  close (the widget shows a *Prev* column).
  Check a new symbol on tradingview.com first: `BINANCE:TONUSDT` showed "No data". Stock prices are
  delayed in the free widget (a small **D** after the price). The widget is rebuilt when the page or the
  theme changes, because its colours are fixed at creation. Opening a price page still refreshes the
  tab counts.
- **Day chart pop-up.** The quotes table is a cross-origin iframe, so the page can't see clicks inside
  it (they would open a TradingView tab; the widget's `largeChartUrl` option only changes which page
  that new tab shows). `rowButtons()` lays one transparent `<button class="quote-row">` over each row
  instead, at the offsets in `QUOTE_ROW` (`top: 52`, `height: 35.8` px, measured on 2026-11-20 and the
  same at 390 px and 1280 px widths). A click calls `openChart()`, which fills `#chart-dialog` with
  TradingView's *Advanced Chart* widget (`embed-widget-advanced-chart.js`, `interval: "D"`, candles,
  current theme, symbol change off). Closing the dialog (✕, Esc, backdrop) empties it, which stops the
  chart. The buttons are focusable, so Tab + Enter works too.

## 3. Crypto Fear & Greed Index

- **Crypto Fear & Greed Index** (`#fng`, in the `#prices` section under the note) shows on Crypto Prices
  only: `mountPrices` unhides it and calls `mountFearGreed()` (`feargreed.js`). It reads
  `GET /api/feargreed` (reused for an hour in the page): today's value and label, a 0-100 scale in the
  five bands alternative.me uses (0-25 Extreme Fear, 26-46 Fear, 47-54 Neutral, 55-75 Greed, 76-100
  Extreme Greed), yesterday / last week / last month, and an SVG line chart with the bands behind it, a
  crosshair and a tooltip. The range (30D, 90D, 1Y, All) is kept in `localStorage` (`fngRange`), and the
  chart redraws when its box resizes. Fear is `--accent` (red), greed is `--greed-strong`, a teal-leaning
  green (`#008c70` light, `#10a896` dark): the site's `--business` green sat too close to the red for
  deuteranopes (OKLab Delta E 6.7 against a target of 8), the new ones measure 11.6 and 9.7. Every colour
  also has its label beside it.

## 4. FedWatch

- **FedWatch** (`#fedwatch-btn`, in the Markets menu) is also a `PRICE_PAGES` entry, but with its own
  `section` (`#fedwatch`) and a `mount` function (`mountFedWatch` in `fedwatch.js`) instead of a
  TradingView table. It reads `GET /api/fedwatch` (reused for 5 minutes in the page), shows the next
  decision in ET and in the PC's time, a days/hours/min/sec countdown that ticks only while the page is
  on screen, the odds as one bar per outcome (one colour, every bar labelled, hover text), and the later
  meetings. When the countdown reaches zero it fetches again, which moves it on to the next meeting.

### How the odds are worked out (`news/fedwatch.py`)

CME's FedWatch page sends `frame-ancestors` with a list of partner sites, and the QuikStrike tool inside
it refuses requests without a CME referrer, so neither can be embedded. The odds use CME's published
method instead:

1. **Meetings** come from the Fed's calendar page (`parse_calendar`): the last day of each meeting, 2:00
   pm ET (`zoneinfo`, so summer time is right; Windows needs the `tzdata` package). Notation votes are
   skipped; "Apr/May 30-1" ends in May; a `*` means new projections.
2. **Today's target range** and effective rate (EFFR) come from the New York Fed's API.
3. **Futures**: `ZQ` + month code + year (`ZQZ26` = December 2026), from Yahoo's chart API as
   `ZQZ26.CBT`. Each settles on 100 minus the month's average EFFR.
4. **Rates around the meeting** (`meeting_rates`): with `N` days in the month and the decision on day
   `d`, the old rate holds `d` days and the new one `N - d`. If the month before has no meeting, its
   contract gives the start rate and the meeting month gives the end rate; else, if the month after has
   no meeting, it gives the end rate; else today's EFFR is the start. A decision on the month's last day
   takes its end rate from the next month.
5. **Odds** (`outcome_odds`): the move in 25 bp steps is split between the two nearest whole steps
   (-0.78 steps = 78 % a 25 bp cut, 22 % no change), labelled as target ranges from today's.

Answers are cached in memory: the calendar for 24 h, the rate for 3 h, quotes for 10 minutes. If a
source fails, its last good answer is used; with none, the page names the missing part and shows the
rest. On 23 Nov 2026 it gave 9 Dec: 90 % a 25 bp hike to 4.00-4.25 % (ZQX26 96.12, ZQZ26 95.96), and
the curve agreed (Jan 4.135 %, Feb 4.27 %). CME's own page couldn't be fetched to compare.

## 5. BTC ETF

- **BTC ETF** (`#etf-btn`, first in the Markets menu) is a `PRICE_PAGES` entry with its own `section` (`#etf`) and
  `mount` (`mountEtf` in `etf.js`), like FedWatch; `selectTab` shows the section of whichever such page is
  open and hides the rest. It reads `GET /api/etf` (reused for 10 minutes in the page; at once again if
  the last try had no key or failed): four cards with the day's totals and a table of the funds, largest
  first. Ratios from the server (fee, premium / discount) are shown as percents. Inflows are coloured
  (`--greed-strong` in, `--accent` out) and always carry a + or − sign, so colour is never the only cue.
  A fund with no figures this time is listed with dashes and named in the note above. A column with no
  figures for any fund is hidden (SoSoValue sent no premium / discount at all on 23 Nov 2026, so that
  column is off until it does: class `no-prem` on the table). With no key, the
  `#etf-setup` card gives the steps, with the `.env` file's full path.
- **Daily net inflow chart** (`#etf-flows-card`, between the totals and the table): one bar per trading
  day for all the funds together, from the `history` that `/api/etf` already carries (SoSoValue's
  daily totals: about the last 20 trading days, as its API keeps one month), so it costs no extra
  request. Bars grow from a zero line: up and `--greed-strong` for money in, down and `--accent` for
  money out (the pair checked for colour-blind separation for the Fear & Greed chart), 2 px apart, with
  4 px rounded ends away from the line. The y axis gets round steps (`niceStep`: 1, 2, 2.5 or 5 × a power
  of ten). Hovering a day (a full-height invisible target per bar) outlines its bar and shows the date
  and the signed amount; the note above gives the period's total, and the chart's `aria-label` names
  the biggest inflow and outflow. It redraws when its box resizes. Drawing uses `svg()` from
  `feargreed.js` and the F&G chart's grid, axis and tooltip classes.

## 6. Gold TH Price

- **Gold TH Price** (`#goldth-btn`, last in the Markets menu) is a `PRICE_PAGES` entry with its own
  `section` (`#goldth`) and `mount` (`mountGoldTh` in `goldth.js`), like BTC ETF, whose cards
  (`.etf-stat`) and table (`.etf-table`) it reuses. It reads `GET /api/goldth` (reused for 5 minutes in
  the page, and re-checked every minute while the page is open, so a new announcement shows within about
  5 minutes): four cards (bar and ornament, sell and buy back), today's change and the change since the
  last announcement, and a table of today's announcements, newest first. Up is `--greed-strong` with +,
  down `--accent` with −. Times are shown in Bangkok time whatever the PC's zone.
- **Where the prices come from (`news/goldth.py`).** ทองคำราคา.com (`xn--42cah7d0cxcvbbb9x.com`) has no
  API, so `parse` reads its home page with the standard library's `HTMLParser`: the table inside
  `div.divgta` is the latest announcement (bar and ornament buy / sell, today's change, the change since
  the last one, the Thai date, time and round number), and `table.pdtable` lists today's rounds (time,
  round, bar buy / sell, ornament tax base / sell, gold spot in USD/oz, baht per dollar, change). Changes
  in the table carry no minus sign; the arrow image (`img-down`) gives the direction. Years are Buddhist
  era (2569 = 2026). The table is updated a little after the box, so when the box has a newer round it is
  put on top, with no spot price or baht rate (shown as dashes). Prices are baht per baht-weight
  (15.244 g) of 96.5 % gold.

## 7. Caveats

- **BTC ETF figures come from SoSoValue, not CoinGlass.** CoinGlass fills its page from a private API.
  SoSoValue's docs don't state the units of `sponsor_fee` and `prem_dsc`; they are ratios (0.0025 =
  0.25 %): ✅ checked on real data, IBIT's fee 0.0025. Some figures are SoSoValue's own: FBTC's fee comes
  as 0, and `prem_dsc` was empty for every fund. Flows and net assets settle a day late (T+1).
- **A BTC ETF refresh is all or nothing when SoSoValue refuses.** No connection, a refused key or the
  rate limit (`EtfAbort`) stops the refresh at once, without asking for the remaining funds, and so does
  a refresh where more than half the funds came back without figures. Then the last complete table stays
  on the page and the next try waits `RETRY_AFTER`. One fund with a bad answer is listed with dashes.
- **FedWatch odds are worked out here, not taken from CME.** They follow CME's method but use delayed
  Yahoo quotes and today's EFFR, so they can differ a little from CME's page. Yahoo's chart API is
  unofficial and could change; then the page says the futures are missing and still shows the
  countdown. If the Fed redesigns its calendar page, `parse_calendar` finds no meetings and says so.
- **Gold TH Price reads a web page, not an API.** If ทองคำราคา.com changes its layout, `parse` raises
  `GoldThError` ("the page has changed") and the page says so; the last good answer is kept while the
  server runs. `pytest --live` checks the real page (`test_live_site_still_parses`). The figures are the
  site's copy of the association's announcements, so they can trail the association by a few minutes.
- **The price-row buttons assume TradingView's layout.** If TradingView changes the Market Quotes row
  height or header, clicks can land on the wrong row. The chart pop-up's title names the symbol, so this
  shows at once, and `pytest --live` ([developer guide §9](DEVELOPER-GUIDE.md#9-tests)) checks it directly; re-measure and update `QUOTE_ROW` in
  `prices.js`.
