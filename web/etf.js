// News Forum BTC ETF page: US spot Bitcoin ETFs (flows, net assets, price) from SoSoValue, via /api/etf.
// Loaded before prices.js (which lists it as a page) and app.js; uses app.js's $, el and api and
// feargreed.js's svg() at run time.
// All text goes in with textContent, never innerHTML.
const ETF_RELOAD_MS = 10 * 60 * 1000;   // the server reuses SoSoValue's answer for 30 minutes anyway
let etfData = null;
let etfLoadedAt = 0;
let etfLoading = false;
let etfObserver = null;

function fmtUsd(v, sign = false) {
  if (v === null || v === undefined) return "–";
  const a = Math.abs(v);
  const [d, unit] = a >= 1e9 ? [1e9, "B"] : a >= 1e6 ? [1e6, "M"] : a >= 1e3 ? [1e3, "K"] : [1, ""];
  const s = `$${(a / d).toFixed(unit === "B" || unit === "" ? 2 : 1)}${unit}`;
  return v < 0 ? `−⁠${s}` : sign && v > 0 ? `+⁠${s}` : s;   // word joiner: never break after the sign
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
  renderEtfFlows(d.history || []);
  $("#etf-rows").replaceChildren(...d.funds.map((f, i) => {
    const tr = el("tr");
    const tick = el("td", "etf-ticker", f.ticker);
    tick.title = f.exchange ? `${f.ticker} · ${f.exchange}` : f.ticker;
    const cells = [
      el("td", "num muted", String(i + 1)), tick, el("td", "etf-name", f.name),
      el("td", "num", fmtPct(f.fee)), el("td", "num", f.price === null ? "–" : `$${f.price.toFixed(2)}`),
      el("td", "num etf-prem", fmtPct(f.prem_dsc, true)),
      el("td", `num ${flowClass(f.net_inflow)}`, fmtUsd(f.net_inflow, true)),
      el("td", `num ${flowClass(f.cum_inflow)}`, fmtUsd(f.cum_inflow, true)),
      el("td", "num", fmtUsd(f.net_assets)), el("td", "num", fmtUsd(f.value_traded)),
    ];
    tr.append(...cells);
    return tr;
  }));
  // SoSoValue sends no premium / discount at times; hide the column rather than show a row of dashes
  $("#etf .etf-table").classList.toggle("no-prem", d.funds.every((f) => f.prem_dsc === null));
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

// ---- daily net inflow of all the funds: one bar a trading day, up (green) = in, down (red) = out ----
function renderEtfFlows(hist) {
  $("#etf-flows-card").hidden = !hist.length;
  if (!hist.length) return;
  const total = hist.reduce((s, [, v]) => s + v, 0);
  $("#etf-flows-note").textContent = `All US spot Bitcoin ETFs, last ${hist.length} trading days: `
    + `${fmtUsd(total, true)} in total. Green above the line is money in, red below is money out.`;
  if (!etfObserver) {
    etfObserver = new ResizeObserver(() => etfData && etfData.history && etfData.history.length && drawEtfFlows(etfData.history));
    etfObserver.observe($("#etf-flows"));
  }
  drawEtfFlows(hist);
}

function niceStep(raw) {
  const pow = 10 ** Math.floor(Math.log10(raw || 1));
  return [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= raw);
}

// A bar with 4px rounded corners on its data end only; the end on the zero line stays square.
function barPath(x, w, yBase, yEnd) {
  const up = yEnd < yBase, h = Math.abs(yBase - yEnd), r = Math.min(4, w / 2, h);
  const s = up ? 1 : -1, yTip = yEnd + s * r;
  return `M${x},${yBase}V${yTip}Q${x},${yEnd} ${x + r},${yEnd}H${x + w - r}Q${x + w},${yEnd} ${x + w},${yTip}V${yBase}Z`;
}

function drawEtfFlows(hist) {
  const box = $("#etf-flows");
  const W = Math.max(280, box.clientWidth), H = 200, pad = { l: 58, r: 8, t: 10, b: 24 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const vals = hist.map(([, v]) => v);
  const top = Math.max(0, ...vals), bot = Math.min(0, ...vals);
  const step = niceStep((top - bot) / 4);
  const hi = Math.ceil(top / step) * step || step, lo = Math.floor(bot / step) * step;
  const y = (v) => pad.t + ((hi - v) / (hi - lo)) * ih;
  const slot = iw / hist.length, bw = Math.max(2, slot - 2);   // 2px gap between bars
  const chart = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "fng-svg", role: "img" });

  for (let v = lo; v <= hi + step / 2; v += step) {
    chart.append(svg("line", { x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), class: Math.abs(v) < step / 2 ? "etf-zero" : "fng-grid" }));
    const t = svg("text", { x: pad.l - 6, y: y(v) + 4, class: "fng-axis", "text-anchor": "end" });
    t.textContent = Math.abs(v) < step / 2 ? "$0" : fmtUsd(v).replace(/\.0+([KMB])$/, "$1");   // $250M, not $250.0M
    chart.append(t);
  }
  const ticks = hist.length > 2 ? [0, Math.floor((hist.length - 1) / 2), hist.length - 1] : [...hist.keys()];
  for (const [n, i] of ticks.entries()) {
    const t = svg("text", { x: pad.l + i * slot + slot / 2, y: H - 6, class: "fng-axis",
      "text-anchor": n === 0 ? "start" : n === ticks.length - 1 ? "end" : "middle" });
    t.textContent = etfDay(hist[i][0]).replace(/,? \d{4}$/, "");
    chart.append(t);
  }

  const tip = el("div", "fng-tip");
  tip.hidden = true;
  const bars = hist.map(([date, v], i) => {
    const x = pad.l + i * slot + (slot - bw) / 2;
    const bar = svg("path", { d: barPath(x, bw, y(0), y(v)), class: `etf-bar ${v >= 0 ? "in" : "out"}` });
    const hit = svg("rect", { x: pad.l + i * slot, y: pad.t, width: slot, height: ih, class: "etf-hit" });
    hit.addEventListener("pointerenter", () => {
      bars.forEach((b) => b.classList.toggle("active", b === bar));
      tip.replaceChildren(el("span", "muted", etfDay(date)), el("strong", flowClass(v), fmtUsd(v, true)),
        el("span", null, v > 0 ? "in" : v < 0 ? "out" : "no change"));
      tip.hidden = false;
      const r = chart.getBoundingClientRect();
      tip.style.left = `${Math.min(Math.max(((x + bw / 2) / W) * r.width, 80), r.width - 80)}px`;
      tip.style.top = `${(Math.min(y(v), y(0)) / H) * r.height}px`;
    });
    chart.append(bar);
    chart.append(hit);
    return bar;
  });
  chart.addEventListener("pointerleave", () => { tip.hidden = true; bars.forEach((b) => b.classList.remove("active")); });

  const most = Math.max(...vals), least = Math.min(...vals);
  chart.setAttribute("aria-label", `Daily net inflow of all US spot Bitcoin ETFs from ${etfDay(hist[0][0])} to `
    + `${etfDay(hist[hist.length - 1][0])}: biggest inflow ${fmtUsd(most, true)} on ${etfDay(hist[vals.indexOf(most)][0])}, `
    + `biggest outflow ${fmtUsd(least, true)} on ${etfDay(hist[vals.indexOf(least)][0])}.`);
  box.replaceChildren(chart, tip);
}
