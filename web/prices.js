// News Forum price pages (Crypto Prices / Stock Prices). Loaded before app.js; uses its $ and el helpers at run time.
// ---- Crypto Prices / Stock Prices / Currency to THB: TradingView's free "Market Quotes" widget ----
// A page with `chart` also shows that symbol's Advanced Chart under the table.
// Each page is picked from the "Markets" drop-down at the top right (index.html). Symbols are TradingView "EXCHANGE:TICKER" names.
const PRICE_PAGES = {
  etf: { section: "#etf", mount: () => mountEtf() },                // etf.js
  fedwatch: { section: "#fedwatch", mount: () => mountFedWatch() },  // fedwatch.js
  goldth: { section: "#goldth", mount: () => mountGoldTh() },        // goldth.js
  calendar: { section: "#calendar", mount: () => mountCalendar() },  // below, TradingView's Economic Calendar
  prices: {
    group: "Crypto",
    link: "https://www.tradingview.com/markets/cryptocurrencies/",
    detail: "in US dollars (Binance, against USDT). Change is since the start of the day (UTC).",
    symbols: [
      ["BINANCE:BTCUSDT", "Bitcoin"], ["BINANCE:ETHUSDT", "Ethereum"], ["BINANCE:BNBUSDT", "BNB"],
      ["BINANCE:SOLUSDT", "Solana"], ["BINANCE:XRPUSDT", "XRP"], ["BINANCE:DOGEUSDT", "Dogecoin"],
      ["BINANCE:ADAUSDT", "Cardano"], ["BINANCE:TRXUSDT", "TRON"], ["BINANCE:LTCUSDT", "Litecoin"],
      ["BINANCE:AVAXUSDT", "Avalanche"], ["BINANCE:LINKUSDT", "Chainlink"], ["BINANCE:DOTUSDT", "Polkadot"],
      ["BINANCE:OPUSDT", "Optimism (OP)"], ["BINANCE:ARBUSDT", "Arbitrum (ARB)"],
    ],
  },
  stocks: {
    group: "Tech stocks",
    link: "https://www.tradingview.com/markets/stocks-usa/",
    detail: "Gold (XAU/USD, spot, per troy ounce) and US-listed tech stocks, in US dollars. A small D next to a price means it is delayed (free stock data is not real-time). Change is since the previous close; outside US trading hours the last price is shown.",
    symbols: [
      ["OANDA:XAUUSD", "Gold (XAU/USD)"],
      ["NASDAQ:ANT", "Anthropic"], ["NASDAQ:AAPL", "Apple"], ["NASDAQ:MSFT", "Microsoft"], ["NASDAQ:NVDA", "Nvidia"],
      ["NASDAQ:GOOGL", "Alphabet (Google)"], ["NASDAQ:AMZN", "Amazon"], ["NASDAQ:META", "Meta"],
      ["NASDAQ:TSLA", "Tesla"], ["NASDAQ:AVGO", "Broadcom"], ["NYSE:TSM", "TSMC"],
      ["NASDAQ:AMD", "AMD"], ["NYSE:ORCL", "Oracle"], ["NASDAQ:NFLX", "Netflix"],
      ["NASDAQ:ASML", "ASML"], ["NASDAQ:INTC", "Intel"],
    ],
  },
  currency: {
    group: "Thai baht",
    link: "https://www.tradingview.com/symbols/USDTHB/",
    detail: "in Thai baht for one unit of each currency (FX_IDC: interbank rates, not a bank's buying or selling rates). "
      + "The yen is per 1 yen; Thai banks quote it per 100 yen, so multiply by 100 to compare. "
      + "Change is since the previous daily close. The chart below is USD to THB on daily candles; change the interval in its toolbar.",
    symbols: [
      ["FX_IDC:USDTHB", "USD to THB (Dollar)"], ["FX_IDC:JPYTHB", "JPY to THB (Yen)"],
      ["FX_IDC:EURTHB", "EUR to THB (Euro)"], ["FX_IDC:GBPTHB", "GBP to THB (Pound)"],
    ],
    chart: "FX_IDC:USDTHB",
  },
};
let pricesShown = null;   // "view/theme" of the widget on screen; it live-updates by itself

function currentTheme() {
  return document.documentElement.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

function mountPrices(view) {
  const page = PRICE_PAGES[view];
  if (page.mount) { page.mount(); return; }   // a page with its own section, not a TradingView table
  $("#fng").hidden = view !== "prices";        // the Fear & Greed panel (feargreed.js) is on Crypto Prices only
  if (view === "prices") mountFearGreed();
  const theme = currentTheme();
  if (pricesShown === `${view}/${theme}`) return;
  pricesShown = `${view}/${theme}`;
  $("#prices-source").href = page.link;
  $("#prices-detail").textContent = page.detail;
  const box = el("div", "tradingview-widget-container");
  const script = document.createElement("script");
  script.src = "https://s3.tradingview.com/external-embedding/embed-widget-market-quotes.js";
  script.async = true;
  script.textContent = JSON.stringify({
    width: "100%", height: 36 * page.symbols.length + 110, locale: "en", colorTheme: theme, isTransparent: true,
    showSymbolLogo: true,
    symbolsGroups: [{ name: page.group, symbols: page.symbols.map(([name, displayName]) => ({ name, displayName })) }],
  });
  box.append(el("div", "tradingview-widget-container__widget"), script);
  $("#prices-widget").replaceChildren(box, rowButtons(page));
  $("#prices-chart").hidden = !page.chart;
  $("#prices-chart").replaceChildren(...(page.chart ? [chartWidget(page.chart, theme)] : []));
}

// ---- Economic Calendar: TradingView's free "Economic Calendar" widget (the same data as
// https://www.tradingview.com/economic-calendar/). Times show in this PC's time zone. ----
const CALENDAR_COUNTRIES = "us,eu,gb,de,fr,it,jp,cn,kr,in,id,th,au,ca,br,mx,za,tr,sa,ru,ar";
let calendarShown = null;   // theme of the widget on screen; it updates by itself

function mountCalendar() {
  const theme = currentTheme();
  if (calendarShown === theme) return;
  calendarShown = theme;
  const box = el("div", "tradingview-widget-container calendar-widget");
  const script = document.createElement("script");
  script.src = "https://s3.tradingview.com/external-embedding/embed-widget-events.js";
  script.async = true;
  script.textContent = JSON.stringify({
    width: "100%", height: "100%", locale: "en", colorTheme: theme, isTransparent: true,
    importanceFilter: "-1,0,1", countryFilter: CALENDAR_COUNTRIES,
  });
  box.append(el("div", "tradingview-widget-container__widget"), script);
  $("#calendar-widget").replaceChildren(box);
}

// ---- click a row → day chart pop-up ----
// The quotes table is an iframe from tradingview.com, so this page can't see clicks inside it (they would
// open a new TradingView tab). Invisible buttons laid over its rows catch the clicks instead.
const QUOTE_ROW = { top: 52, height: 35.8 };   // measured from the widget; the same at every page width

function rowButtons(page) {
  const layer = el("div", "quote-rows");
  layer.style.top = `${QUOTE_ROW.top}px`;
  for (const [symbol, name] of page.symbols) {
    const b = el("button", "quote-row");
    b.type = "button";
    b.style.height = `${QUOTE_ROW.height}px`;
    b.title = `${name}: open the day chart`;
    b.setAttribute("aria-label", `Day chart: ${name}`);
    b.addEventListener("click", () => openChart(symbol, name));
    layer.append(b);
  }
  return layer;
}

// TradingView's free "Advanced Chart" widget, on daily candles (interval "D").
function openChart(symbol, name) {
  $("#chart-title").textContent = name;
  $("#chart-symbol").textContent = `${symbol} · Day chart`;
  $("#chart-box").replaceChildren(chartWidget(symbol, currentTheme()));
  $("#chart-dialog").showModal();
}

function chartWidget(symbol, theme) {
  const box = el("div", "tradingview-widget-container chart-widget");
  const script = document.createElement("script");
  script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
  script.async = true;
  script.textContent = JSON.stringify({
    autosize: true, symbol, interval: "D", timezone: "Etc/UTC", theme, style: "1",
    locale: "en", allow_symbol_change: false, hide_side_toolbar: true, save_image: false, calendar: false,
    support_host: "https://www.tradingview.com",
  });
  box.append(el("div", "tradingview-widget-container__widget chart-widget"), script);
  return box;
}

function closeChart() { $("#chart-dialog").close(); }

addEventListener("DOMContentLoaded", () => {   // after app.js, whose $ helper this uses
  const dlg = $("#chart-dialog");
  $("#chart-close").addEventListener("click", closeChart);
  dlg.addEventListener("click", (e) => { if (e.target === dlg) closeChart(); });   // backdrop
  dlg.addEventListener("close", () => $("#chart-box").replaceChildren());          // stop the chart
});
