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
  c.dataset.id = a.id;   // lets the keyboard shortcuts find a story's card again after a re-render
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

async function loadCounts() {
  renderCounts((await api("/api/articles?view=today")).counts);
}

async function load() {
  $("#new-bar").hidden = true;                  // the list is about to show everything there is
  newSinceShown = 0;
  if (state.view in PRICE_PAGES) { await loadCounts(); return; }   // no stories on a price page
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

// ---- refresh: on page open, the Refresh button, and every 2 hours while the page stays open ----
const AUTO_REFRESH_MS = 2 * 60 * 60 * 1000;
let lastRefreshAt = Date.now();   // in memory, so a blocked localStorage can't cause a refresh every minute
let refreshing = false;
let newSinceShown = 0;            // stories fetched by auto-refreshes and not yet shown in the list

// auto = true: fetch in the background and leave the list alone; a bar offers the new stories instead.
async function refresh(force, auto = false) {
  if (refreshing) return;
  refreshing = true;
  lastRefreshAt = Date.now();
  const btn = $("#refresh");
  btn.disabled = true; btn.textContent = "Fetching…";
  try {
    const r = await api(`/api/refresh?force=${force}`, { method: "POST" });
    const errs = Object.entries(r.errors || {});
    const alert = $("#feed-alert");
    alert.hidden = !errs.length;
    alert.textContent = errs.length ? `Couldn't reach ${errs.map(([n]) => n).join(", ")} this time. Other sources are fine.` : "";
    store("lastRefresh", new Date().toISOString());
    if (auto && r.new) newSinceShown += r.new;
  } catch (e) {
    $("#feed-alert").hidden = false;
    $("#feed-alert").textContent = "Refresh failed: " + e.message;
  } finally {
    btn.disabled = false; btn.textContent = "Refresh";
    refreshing = false;
    showUpdated();
    checkHealth();
    if (auto) { await loadCounts(); showNewBar(); } else await load();
  }
}

function showNewBar() {
  if (!newSinceShown || state.view in PRICE_PAGES) return;
  $("#new-bar-text").textContent = `${newSinceShown} new stor${newSinceShown > 1 ? "ies" : "y"} since this list was loaded`;
  $("#new-bar").hidden = false;
}

function autoRefreshIfDue() {
  if (Date.now() - lastRefreshAt >= AUTO_REFRESH_MS) refresh(false, true);
}

function showUpdated() {
  const t = store("lastRefresh");
  $("#updated").textContent = t ? `Updated ${timeAgo(t)}` : "";
}

// ---- feed health: a feed is a problem when its last fetch failed or brought back no stories ----
function feedProblem(f) {
  if (f.error) return f.last_ok ? `${f.error} (last worked ${timeAgo(f.last_ok)})` : f.error;
  if (f.last_fetch && !f.last_count) return "Feed returned no stories";
  return null;
}

let feedList = [];

async function checkHealth() {
  try { feedList = (await api("/api/status")).feeds; } catch (e) { console.error(e); return; }
  $("#tagline").textContent = `International news from ${feedList.length} sources, gathered for you each day.`;
  const bad = feedList.filter(feedProblem).length;
  const h = $("#health");
  h.hidden = false;
  h.classList.toggle("bad", bad > 0);
  h.textContent = bad ? `● ${bad} source${bad > 1 ? "s" : ""} down` : `● ${feedList.length} sources OK`;
  h.title = bad ? "Some feeds failed on the last refresh. Click for details." : "Every feed worked on the last refresh";
}

async function showStatus() {
  await checkHealth();
  const tb = $("#status-table tbody");
  tb.replaceChildren();
  const rows = feedList.map((f) => ({ f, problem: feedProblem(f) }))
    .sort((a, b) => Boolean(b.problem) - Boolean(a.problem));   // problems first, otherwise feeds.json order
  for (const { f, problem } of rows) {
    const tr = el("tr", problem ? "problem" : null);
    const state_ = problem ? el("td", "bad", `● ${problem}`)
      : el("td", f.last_fetch ? "ok" : "muted", f.last_fetch ? "● OK" : "Not fetched yet");
    tr.append(el("td", null, f.name), el("td", null, CATEGORY_LABEL[f.category]),
      el("td", null, f.last_fetch ? timeAgo(f.last_fetch) : "—"), el("td", null, String(f.last_count ?? 0)), state_);
    tb.append(tr);
  }
  if (!$("#status-dialog").open) $("#status-dialog").showModal();
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
  $("#health").addEventListener("click", showStatus);
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
  setInterval(() => { showUpdated(); autoRefreshIfDue(); }, 60000);   // checked each minute, so it catches up after sleep
  document.addEventListener("visibilitychange", () => { if (!document.hidden) autoRefreshIfDue(); });
  $("#new-bar-show").addEventListener("click", async () => {
    await load();
    $(".tabs").scrollIntoView({ behavior: "smooth" });
  });

  const saved = store("view");
  selectTab(["today", "saved", ...Object.keys(PRICE_PAGES), ...Object.keys(CATEGORY_LABEL)].includes(saved) ? saved : "today");
  showUpdated();
  refresh(false); // fetch only sources older than 30 minutes
}

init();
