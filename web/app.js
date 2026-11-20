// News Forum front end. All article text is inserted with textContent (never innerHTML).
const $ = (s) => document.querySelector(s);
const state = { view: "today", articles: [], source: "", hideRead: false, q: "" };
const CATEGORY_LABEL = {
  world: "World", business: "Business", markets: "Crypto & Investing", asia: "Asia", tech: "AI",
};

function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch { return null; }
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

function timeAgo(iso) {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h} h ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function dayLabel(iso) {
  const d = new Date(iso), today = new Date();
  const yest = new Date(); yest.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yest.toDateString()) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function safeUrl(u) {
  try { const p = new URL(u); return p.protocol === "http:" || p.protocol === "https:" ? p.href : null; }
  catch { return null; }
}

function card(a) {
  const c = el("article", "card" + (a.is_read ? " read" : ""));
  const body = el("div", "card-body");

  const meta = el("div", "meta");
  if (state.view === "today" || state.view === "saved") meta.append(el("span", `tag ${a.category}`, CATEGORY_LABEL[a.category]), el("span", null, "·"));
  meta.append(el("span", "src", a.source), el("span", null, "·"), el("time", null, timeAgo(a.published)));
  meta.lastChild.dateTime = a.published;

  const h = el("h2", "headline");
  const link = el("a", null, a.title);
  const href = safeUrl(a.link);
  if (href) { link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer"; }
  link.addEventListener("click", () => { if (!a.is_read) setFlag(a, "read", true); });
  h.append(link);

  body.append(meta, h);
  if (a.summary) body.append(el("p", "summary", a.summary));

  const actions = el("div", "actions");
  const star = el("button", "star" + (a.saved ? " on" : ""), a.saved ? "★ Saved" : "☆ Save");
  star.type = "button";
  star.addEventListener("click", () => setFlag(a, "saved", !a.saved));
  const read = el("button", null, a.is_read ? "Mark unread" : "Mark read");
  read.type = "button";
  read.addEventListener("click", () => setFlag(a, "read", !a.is_read));
  actions.append(star, read);
  body.append(actions);
  c.append(body);

  const img = safeUrl(a.image);
  if (img) {
    const t = el("img", "thumb");
    t.loading = "lazy"; t.alt = ""; t.referrerPolicy = "no-referrer"; t.src = img;
    t.addEventListener("error", () => t.remove());
    c.append(t);
  }

  // Clicking the card (anywhere except the headline link or a button) opens the reader pop-up.
  c.tabIndex = 0;
  c.setAttribute("aria-label", `${a.title}. Press Enter for details`);
  c.addEventListener("click", (e) => { if (!e.target.closest("a, button")) openReader(a); });
  c.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target === c) openReader(a); });
  return c;
}

// ---- reader pop-up -------------------------------------------------------
let readerToken = 0;
let readerArticle = null;

function fullDate(iso) {
  return new Date(iso).toLocaleString(undefined,
    { weekday: "short", day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function setReaderSave() {
  const b = $("#reader-save");
  const on = readerArticle && readerArticle.saved;
  b.textContent = on ? "★ Saved" : "☆ Save";
  b.classList.toggle("on", !!on);
}

// ---- key-sentence highlighting (built from DOM nodes, never innerHTML) ----
let readerParas = [];
let readerMarks = [];   // the story's key sentences, in reading order, exactly as written

function highlightsOn() { return store("highlights") !== "0"; }

function fillParagraphs(paragraphs, marks = readerMarks) {
  readerParas = paragraphs;
  readerMarks = marks;
  const on = highlightsOn();
  $("#reader-text").replaceChildren(...paragraphs.map((text) => {
    const p = el("p");
    let last = 0;
    if (on) for (const sentence of marks) {
      const i = text.indexOf(sentence, last);
      if (i < 0) continue;
      if (i > last) p.append(text.slice(last, i));
      p.append(el("mark", "key", sentence));
      last = i + sentence.length;
    }
    p.append(text.slice(last));
    return p;
  }));
}

function showImage(url) {
  const img = $("#reader-image");
  const safe = safeUrl(url);
  img.hidden = !safe;
  if (safe && img.src !== safe) img.src = safe;
  if (!safe) img.removeAttribute("src");
}

async function openReader(a, retry = false) {
  const token = ++readerToken;
  readerArticle = a;
  const dlg = $("#reader");

  // Header straight from the list data, so the pop-up opens instantly.
  $("#reader-meta").replaceChildren(
    el("span", `tag ${a.category}`, CATEGORY_LABEL[a.category]), el("span", null, "·"),
    el("span", "src", a.source), el("span", null, "·"), el("span", null, timeAgo(a.published)));
  $("#reader-title").textContent = a.title;
  $("#reader-byline").textContent = fullDate(a.published);
  $("#reader-tags").replaceChildren();
  showImage(a.image);
  const notice = $("#reader-notice");
  notice.hidden = false;
  notice.className = "reader-notice loading";
  notice.textContent = `Loading the full story from ${a.source}…`;
  fillParagraphs(a.summary ? [a.summary] : [], []);
  const open = $("#reader-open");
  const href = safeUrl(a.link);
  if (href) open.href = href; else open.removeAttribute("href");
  open.textContent = `Read on ${a.source} ↗`;
  setReaderSave();
  if (!dlg.open) dlg.showModal();
  dlg.querySelector(".reader-body").scrollTop = 0;
  if (!a.is_read) setFlag(a, "read", true);

  let data;
  try {
    data = await api(`/api/articles/${a.id}/detail${retry ? "?retry=true" : ""}`);
  } catch (e) {
    if (token !== readerToken) return;
    notice.className = "reader-notice";
    notice.textContent = "Couldn't load the details: " + e.message;
    return;
  }
  if (token !== readerToken) return; // the user opened another story meanwhile

  const art = data.article, rd = data.reader;
  const author = (rd.ok && rd.author) || art.author;
  $("#reader-byline").textContent = [author ? `By ${author}` : null, fullDate(art.published)].filter(Boolean).join(" · ");
  $("#reader-tags").replaceChildren(...(art.tags || []).map((t) => el("span", "chip", t)));
  showImage((rd.ok && rd.image) || art.image);

  const marks = data.highlights || [];
  if (rd.ok) {
    notice.hidden = true;
    fillParagraphs(rd.paragraphs, marks);
    return;
  }
  const fallback = data.feed_text.length ? data.feed_text : (art.summary ? [art.summary] : []);
  fillParagraphs(fallback, marks);
  notice.className = "reader-notice";
  notice.replaceChildren(
    el("strong", null, "Full story not available here. "),
    el("span", null, `${rd.error}. Showing what ${art.source}'s feed provides — use the button below for the whole article. `));
  const again = el("button", "linkish", "Try again");
  again.type = "button";
  again.addEventListener("click", () => openReader(a, true));
  notice.append(again);
}

function closeReader() {
  readerToken++;
  $("#reader").close();
}

function visible() {
  return state.articles.filter((a) =>
    (!state.hideRead || !a.is_read) && (!state.source || a.source === state.source));
}

function render() {
  const list = $("#list");
  list.replaceChildren();
  const items = visible();
  let lastDay = null;
  for (const a of items) {
    const day = dayLabel(a.published);
    if (state.view !== "today" && day !== lastDay) { list.append(el("div", "day-label", day)); lastDay = day; }
    list.append(card(a));
  }
  const empty = $("#empty");
  empty.hidden = items.length > 0;
  if (!items.length) {
    empty.textContent = state.view === "saved" ? "Nothing saved yet. Use ☆ Save on a story to keep it here."
      : state.q ? "No headlines match your search."
      : state.hideRead && state.articles.length ? "You're all caught up." : "No news here yet. Try Refresh.";
  }
}

function renderSources() {
  const sel = $("#source");
  const names = [...new Set(state.articles.map((a) => a.source))].sort();
  if (state.source && !names.includes(state.source)) state.source = "";
  sel.replaceChildren(el("option", null, "All sources"));
  sel.firstChild.value = "";
  for (const n of names) { const o = el("option", null, n); o.value = n; sel.append(o); }
  sel.value = state.source;
}

function renderCounts(counts) {
  document.querySelectorAll(".tabs button").forEach((b) => {
    const badge = b.querySelector(".count");     // every news tab has one
    const n = counts[b.dataset.view] || 0;
    if (badge) badge.textContent = n ? String(n) : "";
  });
}

async function load() {
  if (state.view in PRICE_PAGES) {              // no stories on a price page: just keep the counts fresh
    renderCounts((await api("/api/articles?view=today")).counts);
    return;
  }
  const params = new URLSearchParams({ view: state.view });
  if (state.q) params.set("q", state.q);
  const data = await api(`/api/articles?${params}`);
  state.articles = data.articles;
  renderCounts(data.counts);
  renderSources();
  render();
}

async function setFlag(a, which, value) {
  const field = which === "read" ? "is_read" : "saved";
  a[field] = value ? 1 : 0;
  render();
  try {
    await api(`/api/articles/${a.id}/${which}`, { method: "POST", body: { value } });
    const data = await api(`/api/articles?view=${state.view}${state.q ? "&q=" + encodeURIComponent(state.q) : ""}`);
    renderCounts(data.counts);
  } catch (e) { console.error(e); }
}

async function refresh(force) {
  const btn = $("#refresh");
  btn.disabled = true; btn.textContent = "Fetching…";
  try {
    const r = await api(`/api/refresh?force=${force}`, { method: "POST" });
    const errs = Object.entries(r.errors || {});
    const alert = $("#feed-alert");
    alert.hidden = !errs.length;
    alert.textContent = errs.length ? `Couldn't reach ${errs.map(([n]) => n).join(", ")} this time. Other sources are fine.` : "";
    store("lastRefresh", new Date().toISOString());
  } catch (e) {
    $("#feed-alert").hidden = false;
    $("#feed-alert").textContent = "Refresh failed: " + e.message;
  } finally {
    btn.disabled = false; btn.textContent = "Refresh";
    showUpdated();
    await load();
  }
}

function showUpdated() {
  const t = store("lastRefresh");
  $("#updated").textContent = t ? `Updated ${timeAgo(t)}` : "";
}

async function showStatus() {
  const { feeds } = await api("/api/status");
  const tb = $("#status-table tbody");
  tb.replaceChildren();
  for (const f of feeds) {
    const tr = el("tr");
    const state_ = f.error ? el("td", "bad", f.error) : el("td", "ok", f.last_fetch ? "OK" : "Not fetched yet");
    tr.append(el("td", null, f.name), el("td", null, CATEGORY_LABEL[f.category]),
      el("td", null, f.last_fetch ? timeAgo(f.last_fetch) : "—"), el("td", null, String(f.last_count ?? 0)), state_);
    tb.append(tr);
  }
  $("#status-dialog").showModal();
}

// ---- Crypto Prices / Stock Prices: TradingView's free "Market Quotes" widget (prices only, no chart) ----
// Each page is opened by its own top-right button, not a tab. Symbols are TradingView "EXCHANGE:TICKER" names.
const PRICE_PAGES = {
  prices: {
    button: "#prices-btn", group: "Crypto",
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
    button: "#stocks-btn", group: "Tech stocks",
    link: "https://www.tradingview.com/markets/stocks-usa/",
    detail: "Gold (XAU/USD, spot, per troy ounce) and US-listed tech stocks, in US dollars. A small D next to a price means it is delayed (free stock data is not real-time). Change is since the previous close; outside US trading hours the last price is shown.",
    symbols: [
      ["OANDA:XAUUSD", "Gold (XAU/USD)"],
      ["NASDAQ:AAPL", "Apple"], ["NASDAQ:MSFT", "Microsoft"], ["NASDAQ:NVDA", "Nvidia"],
      ["NASDAQ:GOOGL", "Alphabet (Google)"], ["NASDAQ:AMZN", "Amazon"], ["NASDAQ:META", "Meta"],
      ["NASDAQ:TSLA", "Tesla"], ["NASDAQ:AVGO", "Broadcom"], ["NYSE:TSM", "TSMC"],
      ["NASDAQ:AMD", "AMD"], ["NYSE:ORCL", "Oracle"], ["NASDAQ:NFLX", "Netflix"],
      ["NASDAQ:ASML", "ASML"], ["NASDAQ:INTC", "Intel"],
    ],
  },
};
let pricesShown = null;   // "view/theme" of the widget on screen; it live-updates by itself

function currentTheme() {
  return document.documentElement.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

function mountPrices(view) {
  const page = PRICE_PAGES[view];
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
  $("#prices-widget").replaceChildren(box);
}

function selectTab(view) {
  state.view = view;
  store("view", view);
  document.querySelectorAll(".tabs button").forEach((b) =>
    b.setAttribute("aria-selected", String(b.dataset.view === view)));
  const prices = view in PRICE_PAGES;
  for (const [v, page] of Object.entries(PRICE_PAGES)) $(page.button).setAttribute("aria-pressed", String(v === view));
  for (const id of ["#list", ".toolbar"]) $(id).hidden = prices;
  if (prices) $("#empty").hidden = true;
  $("#prices").hidden = !prices;
  if (prices) mountPrices(view);
  load();
}

function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t;
  if (state.view in PRICE_PAGES) mountPrices(state.view);  // the widget has its own light/dark colours
}

function init() {
  $("#today-date").textContent = new Date().toLocaleDateString(undefined,
    { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  applyTheme(store("theme"));
  state.hideRead = store("hideRead") === "1";
  $("#hide-read").checked = state.hideRead;

  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => selectTab(b.dataset.view)));
  $("#refresh").addEventListener("click", () => refresh(true));
  for (const [v, page] of Object.entries(PRICE_PAGES)) $(page.button).addEventListener("click", () => selectTab(v));
  $("#theme").addEventListener("click", () => {
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    const cur = document.documentElement.dataset.theme || (dark ? "dark" : "light");
    const next = cur === "dark" ? "light" : "dark";
    applyTheme(next); store("theme", next);
  });
  $("#hide-read").addEventListener("change", (e) => { state.hideRead = e.target.checked; store("hideRead", state.hideRead ? "1" : "0"); render(); });
  $("#source").addEventListener("change", (e) => { state.source = e.target.value; render(); });
  let timer;
  $("#search").addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => { state.q = e.target.value.trim(); load(); }, 250);
  });
  $("#read-all").addEventListener("click", async () => {
    const ids = visible().filter((a) => !a.is_read).map((a) => a.id);
    if (!ids.length) return;
    await api("/api/articles/read-all", { method: "POST", body: { ids } });
    await load();
  });
  $("#show-status").addEventListener("click", showStatus);
  $("#reader-close").addEventListener("click", closeReader);
  $("#reader").addEventListener("click", (e) => { if (e.target === e.currentTarget) closeReader(); }); // backdrop
  $("#reader").addEventListener("cancel", () => { readerToken++; }); // Esc
  $("#reader-hl").checked = highlightsOn();
  $("#reader-hl").addEventListener("change", (e) => {
    store("highlights", e.target.checked ? "1" : "0");
    fillParagraphs(readerParas, readerMarks);
  });
  $("#reader-save").addEventListener("click", async () => {
    if (!readerArticle) return;
    await setFlag(readerArticle, "saved", !readerArticle.saved);
    setReaderSave();
  });
  setInterval(showUpdated, 60000);

  const saved = store("view");
  selectTab(["today", "saved", ...Object.keys(PRICE_PAGES), ...Object.keys(CATEGORY_LABEL)].includes(saved) ? saved : "today");
  showUpdated();
  refresh(false); // fetch only sources older than 30 minutes
}

init();
