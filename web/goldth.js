// News Forum Gold TH Price page: Thai gold prices (Gold Traders Association) from ทองคำราคา.com, via /api/goldth.
// Loaded before prices.js (which lists it as a page) and app.js; uses app.js's $, el and api at run time.
// All text goes in with textContent, never innerHTML.
const GOLD_RELOAD_MS = 5 * 60 * 1000;   // the server reuses the site's page for 5 minutes too
let goldData = null;
let goldLoadedAt = 0;
let goldLoading = false;
let goldTimer = null;

const fmtBaht = (v) => v === null || v === undefined ? "–"
  : v.toLocaleString("en-US", { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: 2 });
const fmtChange = (v) => v === null || v === undefined ? "–"
  : v === 0 ? "0" : `${v > 0 ? "+" : "−"}${fmtBaht(Math.abs(v))}`;
const goldClass = (v) => (v > 0 ? "gold-up" : v < 0 ? "gold-down" : "");
const goldTime = (iso, opts) => new Date(iso).toLocaleString(undefined, { timeZone: "Asia/Bangkok", ...opts });

async function mountGoldTh(force = false) {
  if (!goldTimer) goldTimer = setInterval(() => {   // keep the prices fresh while the page is open
    if ($("#goldth").hidden) { clearInterval(goldTimer); goldTimer = null; } else mountGoldTh();
  }, 60 * 1000);
  if (!force && goldData && Date.now() - goldLoadedAt < GOLD_RELOAD_MS) { renderGoldTh(); return; }
  if (goldLoading) return;
  goldLoading = true;
  const status = $("#gold-status");
  if (!goldData) { status.hidden = false; status.textContent = "Loading Thai gold prices…"; }
  try {
    goldData = await api("/api/goldth");
    goldLoadedAt = goldData.error ? 0 : Date.now();   // try again next time if it didn't work
    renderGoldTh();
  } catch (e) {
    status.hidden = false;
    status.textContent = "Couldn't load Thai gold prices: " + e.message;
  } finally {
    goldLoading = false;
  }
}

function renderGoldTh() {
  const d = goldData;
  $("#gold-source").href = d.source_url;
  $("#gold-status").hidden = !d.error;
  $("#gold-status").textContent = d.error ? `Couldn't load Thai gold prices: ${d.error}` : "";
  $("#gold-body").hidden = !d.latest;
  if (!d.latest) return;
  const g = d.latest;
  $("#gold-when").textContent = `Announcement ${g.round} · `
    + `${goldTime(g.time, { weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })} Bangkok time`;
  $("#gold-totals").replaceChildren(
    goldStat("Gold bar · sell", g.bar_sell), goldStat("Gold bar · buy back", g.bar_buy),
    goldStat("Ornament · sell", g.ornament_sell), goldStat("Ornament · buy back", g.ornament_buy));
  const moves = [["Today", g.change_today], ["Since the last announcement", g.change]];
  $("#gold-moves").replaceChildren(...moves.filter(([, v]) => v !== null).map(([name, v]) => {
    const li = el("li");
    li.append(el("span", "muted", name), el("strong", goldClass(v), `${fmtChange(v)} baht`));
    return li;
  }));
  $("#gold-rounds-note").textContent = `${d.rounds.length} announcement${d.rounds.length === 1 ? "" : "s"} so far today, newest first.`;
  $("#gold-rows").replaceChildren(...d.rounds.map((r) => {
    const tr = el("tr");
    tr.append(
      el("td", null, goldTime(r.time, { hour: "2-digit", minute: "2-digit" })), el("td", "num muted", String(r.round)),
      el("td", "num", fmtBaht(r.bar_buy)), el("td", "num", fmtBaht(r.bar_sell)),
      el("td", "num", fmtBaht(r.ornament_buy)), el("td", "num", fmtBaht(r.ornament_sell)),
      el("td", "num", r.spot === null ? "–" : `$${fmtBaht(r.spot)}`), el("td", "num", r.thb === null ? "–" : r.thb.toFixed(2)),
      el("td", `num ${goldClass(r.change)}`, fmtChange(r.change)));
    return tr;
  }));
}

function goldStat(label, value) {
  const card = el("div", "etf-stat");
  card.append(el("span", "muted", label), el("strong", null, `฿${fmtBaht(value)}`));
  return card;
}
