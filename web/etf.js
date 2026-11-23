// News Forum BTC ETF page: US spot Bitcoin ETFs (flows, net assets, price) from SoSoValue, via /api/etf.
// Loaded before prices.js (which lists it as a page) and app.js; uses app.js's $, el and api at run time.
// All text goes in with textContent, never innerHTML.
const ETF_RELOAD_MS = 10 * 60 * 1000;   // the server reuses SoSoValue's answer for 30 minutes anyway
let etfData = null;
let etfLoadedAt = 0;
let etfLoading = false;

function fmtUsd(v, sign = false) {
  if (v === null || v === undefined) return "–";
  const a = Math.abs(v);
  const [d, unit] = a >= 1e9 ? [1e9, "B"] : a >= 1e6 ? [1e6, "M"] : a >= 1e3 ? [1e3, "K"] : [1, ""];
  const s = `$${(a / d).toFixed(unit === "B" || unit === "" ? 2 : 1)}${unit}`;
  return v < 0 ? `−${s}` : sign && v > 0 ? `+${s}` : s;
}

const fmtPct = (r, sign = false) => r === null || r === undefined ? "–"
  : `${r < 0 ? "−" : sign && r > 0 ? "+" : ""}${Math.abs(r * 100).toFixed(2)}%`;
const flowClass = (v) => (v > 0 ? "etf-in" : v < 0 ? "etf-out" : "");
const etfDay = (iso) => iso
  ? new Date(`${iso}T12:00:00Z`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "–";

async function mountEtf(force = false) {
  if (!force && etfData && Date.now() - etfLoadedAt < ETF_RELOAD_MS) { renderEtf(); return; }
  if (etfLoading) return;
  etfLoading = true;
  const status = $("#etf-status");
  if (!etfData) { status.hidden = false; status.textContent = "Loading the Bitcoin ETF figures…"; }
  try {
    etfData = await api("/api/etf");
    etfLoadedAt = etfData.needs_key || etfData.error ? 0 : Date.now();   // retry next time if it didn't work
    renderEtf();
  } catch (e) {
    status.hidden = false;
    status.textContent = "Couldn't load the Bitcoin ETFs: " + e.message;
  } finally {
    etfLoading = false;
  }
}

function renderEtf() {
  const d = etfData;
  $("#etf-source").href = d.source_url;
  $("#etf-setup").hidden = !d.needs_key;
  if (d.needs_key) {
    $("#etf-key-link").href = d.key_url;
    $("#etf-key-file").textContent = d.env_file;
    $("#etf-key-env").textContent = d.key_env;
  }
  const problem = d.error || (d.missing && d.missing.length
    ? `No figures for ${d.missing.join(", ")} this time.` : "");
  $("#etf-status").hidden = !problem;
  $("#etf-status").textContent = d.error ? `Couldn't load the Bitcoin ETFs: ${d.error}` : problem;
  $("#etf-body").hidden = !d.funds.length;
  if (!d.funds.length) return;
  renderEtfTotals(d.totals);
  $("#etf-rows").replaceChildren(...d.funds.map((f, i) => {
    const tr = el("tr");
    const tick = el("td", "etf-ticker", f.ticker);
    tick.title = f.exchange ? `${f.ticker} · ${f.exchange}` : f.ticker;
    const cells = [
      el("td", "num muted", String(i + 1)), tick, el("td", "etf-name", f.name),
      el("td", "num", fmtPct(f.fee)), el("td", "num", f.price === null ? "–" : `$${f.price.toFixed(2)}`),
      el("td", "num", fmtPct(f.prem_dsc, true)),
      el("td", `num ${flowClass(f.net_inflow)}`, fmtUsd(f.net_inflow, true)),
      el("td", `num ${flowClass(f.cum_inflow)}`, fmtUsd(f.cum_inflow, true)),
      el("td", "num", fmtUsd(f.net_assets)), el("td", "num", fmtUsd(f.value_traded)),
    ];
    tr.append(...cells);
    return tr;
  }));
  const dates = [...new Set(d.funds.map((f) => f.date).filter(Boolean))].sort();
  $("#etf-date").textContent = dates.length ? `Figures for ${etfDay(dates[dates.length - 1])} (US trading day; flows settle the next day).` : "";
}

function renderEtfTotals(t) {
  const cards = t ? [
    ["Total net assets", fmtUsd(t.net_assets), ""],
    ["Daily net inflow", fmtUsd(t.net_inflow, true), flowClass(t.net_inflow)],
    ["Total net inflow", fmtUsd(t.cum_inflow, true), flowClass(t.cum_inflow)],
    ["Daily value traded", fmtUsd(t.value_traded), ""],
  ] : [];
  $("#etf-totals").replaceChildren(...cards.map(([name, value, cls]) => {
    const card = el("div", "etf-stat");
    card.append(el("span", "fw-kicker", name), el("strong", cls, value));
    return card;
  }));
  $("#etf-totals-date").textContent = t ? `All US spot Bitcoin ETFs, ${etfDay(t.date)}` : "";
}
