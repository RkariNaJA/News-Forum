// News Forum keyboard shortcuts. Loaded after app.js and uses its state and functions.
// Shortcuts are off while you type in a box, and in the Source status / shortcuts pop-ups (Esc closes those).
const TAB_ORDER = [...document.querySelectorAll(".tabs button")].map((b) => b.dataset.view);
let currentId = null;   // the story last moved to, so j/k carry on from it after a re-render or the reader

function cards() { return [...document.querySelectorAll("#list .card")]; }
function articleOf(card) { return card && state.articles.find((a) => String(a.id) === card.dataset.id); }

function currentCard() {
  return document.activeElement.closest?.("#list .card")
    || (currentId != null && $(`#list .card[data-id="${currentId}"]`)) || null;
}

function focusCard(c) {
  if (!c) return;
  currentId = c.dataset.id;
  c.focus({ preventScroll: true });
  c.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function moveCard(step) {
  const all = cards();
  if (!all.length) return;
  const i = all.indexOf(currentCard());
  focusCard(all[i < 0 ? (step > 0 ? 0 : all.length - 1) : Math.min(all.length - 1, Math.max(0, i + step))]);
}

// Run a change that re-draws the list, then put the focus back on the same story
// (or on the one now in its place, if "Hide read" took it off the list).
function keepFocus(c, change) {
  const i = cards().indexOf(c);
  change();
  const all = cards();
  focusCard($(`#list .card[data-id="${c.dataset.id}"]`) || all[Math.min(i, all.length - 1)]);
}

function openOnSite(a) {
  const href = a && safeUrl(a.link);
  if (!href) return;
  window.open(href, "_blank", "noopener,noreferrer");
  if (!a.is_read) setFlag(a, "read", true);
}

function moveTab(step) {
  const i = TAB_ORDER.indexOf(state.view);   // -1 on a price page: → goes to Today
  selectTab(TAB_ORDER[(i + step + TAB_ORDER.length) % TAB_ORDER.length]);
}

// Inside the reader pop-up: j/k go to the next/previous story, s saves, o opens the site.
function readerKey(key) {
  if (key === "s") { $("#reader-save").click(); return true; }
  if (key === "o") { openOnSite(readerArticle); return true; }
  if (key !== "j" && key !== "k") return false;
  // Walk the full list, not visible(): with "Hide read" on, the open story is already hidden.
  const list = state.articles.filter((a) => !state.source || a.source === state.source);
  const step = key === "j" ? 1 : -1;
  let n = list.findIndex((a) => a.id === readerArticle?.id) + step;
  while (step > 0 && list[n] && state.hideRead && list[n].is_read) n += step;   // k always goes back one
  const next = list[n];
  if (next) { currentId = String(next.id); openReader(next); }
  return true;
}

function onKey(e) {
  if (e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
  const t = e.target;
  if (t.matches?.("input, textarea, select") || t.isContentEditable) {
    if (e.key === "Escape" && t.id === "search") t.blur();
    return;
  }
  if ($("#reader").open) { if (readerKey(e.key)) e.preventDefault(); return; }
  if (document.querySelector("dialog[open]")) return;

  const onNews = !(state.view in PRICE_PAGES);
  const c = currentCard();
  const handlers = {
    ArrowRight: () => moveTab(1), ArrowLeft: () => moveTab(-1),
    j: () => onNews && moveCard(1), ArrowDown: () => onNews && moveCard(1),
    k: () => onNews && moveCard(-1), ArrowUp: () => onNews && moveCard(-1),
    s: () => c && keepFocus(c, () => { const a = articleOf(c); setFlag(a, "saved", !a.saved); }),
    m: () => c && keepFocus(c, () => { const a = articleOf(c); setFlag(a, "read", !a.is_read); }),
    o: () => c && openOnSite(articleOf(c)),
    "/": () => onNews && $("#search").focus(),
    r: () => refresh(true),
    "?": () => $("#keys-dialog").showModal(),
  };
  if (/^[1-9]$/.test(e.key) && TAB_ORDER[e.key - 1]) handlers[e.key] = () => selectTab(TAB_ORDER[e.key - 1]);
  if (!handlers[e.key]) return;
  e.preventDefault();
  handlers[e.key]();
}

document.addEventListener("keydown", onKey);
document.addEventListener("focusin", (e) => { const c = e.target.closest?.("#list .card"); if (c) currentId = c.dataset.id; });
$("#show-keys").addEventListener("click", () => $("#keys-dialog").showModal());
