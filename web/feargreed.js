// News Forum: Crypto Fear & Greed Index panel on the Crypto Prices page (data: alternative.me, via /api/feargreed).
// Loaded before prices.js, which shows it; uses app.js's $, el, api and store at run time. Text via textContent only.
const FNG_ZONES = [   // alternative.me's bands: 0-25, 26-46, 47-54, 55-75, 76-100
  { max: 25, label: "Extreme Fear", cls: "xfear" }, { max: 46, label: "Fear", cls: "fear" },
  { max: 54, label: "Neutral", cls: "neutral" }, { max: 75, label: "Greed", cls: "greed" },
  { max: 100, label: "Extreme Greed", cls: "xgreed" },
];
const FNG_RANGES = { "30D": 30, "90D": 90, "1Y": 365, "All": Infinity };
const FNG_RELOAD_MS = 60 * 60 * 1000;
const SVG_NS = "http://www.w3.org/2000/svg";
let fngData = null;
let fngLoadedAt = 0;
let fngRange = null;   // read from storage on first mount: store() lives in app.js, loaded after this file
let fngObserver = null;

const fngZone = (v) => FNG_ZONES.find((z) => v <= z.max);
const fngDate = (iso, opts = { day: "numeric", month: "short", year: "numeric" }) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString(undefined, opts);

function svg(tag, attrs = {}) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
}

async function mountFearGreed() {
  if (!fngRange) fngRange = store("fngRange") in FNG_RANGES ? store("fngRange") : "90D";
  if (!fngObserver) {
    fngObserver = new ResizeObserver(() => fngData && drawFngChart());
    fngObserver.observe($("#fng-chart"));
    $("#fng-ranges").replaceChildren(...Object.keys(FNG_RANGES).map((r) => {
      const b = el("button", "btn", r);
      b.type = "button";
      b.addEventListener("click", () => { fngRange = r; store("fngRange", r); renderFng(); });
      return b;
    }));
  }
  if (fngData && Date.now() - fngLoadedAt < FNG_RELOAD_MS) { renderFng(); return; }
  try {
    fngData = await api("/api/feargreed");
    fngLoadedAt = Date.now();
  } catch (e) {
    fngData = { current: null, history: [], error: e.message };
  }
  renderFng();
}

function renderFng() {
  const d = fngData;
  $("#fng-status").hidden = !d.error;
  $("#fng-status").textContent = d.error ? `Couldn't load the Fear & Greed Index: ${d.error}` : "";
  $("#fng-body").hidden = !d.current;
  if (d.source_url) $("#fng-source").href = d.source_url;
  if (!d.current) return;
  const cur = d.current, zone = fngZone(cur.value);
  $("#fng-value").textContent = String(cur.value);
  $("#fng-label").textContent = cur.label;
  $("#fng-label").className = `fng-label ${zone.cls}`;
  $("#fng-date").textContent = `${fngDate(cur.date)} · next update ${d.next_update ? timeUntil(d.next_update) : "daily"}`;
  $("#fng-marker").style.left = `${cur.value}%`;
  const h = d.history, ago = (n) => h[h.length - 1 - n];
  $("#fng-compare").replaceChildren(...[["Yesterday", 1], ["Last week", 7], ["Last month", 30]]
    .filter(([, n]) => ago(n)).map(([name, n]) => {
      const v = ago(n)[1];
      const li = el("li");
      li.append(el("span", "muted", name), el("strong", null, String(v)), el("span", `fng-chip ${fngZone(v).cls}`, fngZone(v).label));
      return li;
    }));
  document.querySelectorAll("#fng-ranges button").forEach((b) => b.setAttribute("aria-pressed", String(b.textContent === fngRange)));
  drawFngChart();
}

function timeUntil(iso) {
  const mins = Math.max(0, Math.round((new Date(iso) - Date.now()) / 60000));
  return mins < 60 ? `in ${mins} min` : `in ${Math.round(mins / 60)} h`;
}

// ---- history line chart (SVG): zones as faint bands, one 2px line, crosshair + tooltip on hover ----
function drawFngChart() {
  const box = $("#fng-chart");
  const all = fngData.history;
  const pts = all.slice(-Math.min(all.length, FNG_RANGES[fngRange]));
  const W = Math.max(280, box.clientWidth), H = 220, pad = { l: 30, r: 10, t: 8, b: 24 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const x = (i) => pad.l + (pts.length > 1 ? (i / (pts.length - 1)) * iw : iw / 2);
  const y = (v) => pad.t + (1 - v / 100) * ih;
  const chart = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "fng-svg", role: "img" });
  let lo = 0;
  for (const z of FNG_ZONES) {   // background bands for each zone, behind everything
    chart.append(svg("rect", { x: pad.l, y: y(z.max), width: iw, height: y(lo) - y(z.max), class: `fng-band ${z.cls}` }));
    lo = z.max;
  }
  for (const v of [0, 25, 50, 75, 100]) {
    chart.append(svg("line", { x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v), class: "fng-grid" }));
    const t = svg("text", { x: pad.l - 6, y: y(v) + 4, class: "fng-axis", "text-anchor": "end" });
    t.textContent = String(v);
    chart.append(t);
  }
  const ticks = pts.length > 1 ? [0, Math.floor((pts.length - 1) / 2), pts.length - 1] : [0];
  const longRange = pts.length > 400;
  for (const [n, i] of ticks.entries()) {
    const t = svg("text", { x: x(i), y: H - 6, class: "fng-axis",
      "text-anchor": n === 0 ? "start" : n === ticks.length - 1 ? "end" : "middle" });
    t.textContent = fngDate(pts[i][0], longRange ? { month: "short", year: "numeric" } : { day: "numeric", month: "short" });
    chart.append(t);
  }
  chart.append(svg("path", { d: pts.map(([, v], i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(""),
    class: "fng-line" }));
  const cross = svg("line", { y1: pad.t, y2: pad.t + ih, class: "fng-cross", visibility: "hidden" });
  const dot = svg("circle", { r: 4.5, class: "fng-dot", visibility: "hidden" });
  chart.append(cross, dot);

  const vals = pts.map((p) => p[1]);
  chart.setAttribute("aria-label", `Fear and Greed Index, ${fngRange === "All" ? "all history" : "last " + fngRange}: `
    + `from ${vals[0]} on ${fngDate(pts[0][0])} to ${vals[vals.length - 1]} today; low ${Math.min(...vals)}, high ${Math.max(...vals)}.`);

  const tip = el("div", "fng-tip");
  tip.hidden = true;
  chart.addEventListener("pointermove", (e) => {
    const r = chart.getBoundingClientRect();
    const px = (e.clientX - r.left) * (W / r.width);
    const i = Math.round(((px - pad.l) / iw) * (pts.length - 1));
    if (i < 0 || i >= pts.length) return;
    const [date, v] = pts[i];
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i));
    dot.setAttribute("cx", x(i)); dot.setAttribute("cy", y(v));
    cross.setAttribute("visibility", "visible"); dot.setAttribute("visibility", "visible");
    tip.replaceChildren(el("span", "muted", fngDate(date)), el("strong", null, String(v)), el("span", null, fngZone(v).label));
    tip.hidden = false;
    const left = (x(i) / W) * r.width;
    tip.style.left = `${Math.min(Math.max(left, 60), r.width - 60)}px`;
    tip.style.top = `${(y(v) / H) * r.height}px`;
  });
  chart.addEventListener("pointerleave", () => {
    tip.hidden = true;
    cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden");
  });
  box.replaceChildren(chart, tip);
}
