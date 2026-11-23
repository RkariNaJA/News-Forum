// News Forum FedWatch page: a countdown to the next FOMC decision and the futures-implied rate odds.
// Loaded before prices.js (which lists it as a page) and app.js; uses app.js's $, el and api at run time.
// All text goes in with textContent, never innerHTML.
const FEDWATCH_REFRESH_MS = 5 * 60 * 1000;   // the server reuses futures quotes for 10 minutes anyway
let fedData = null;
let fedLoadedAt = 0;
let fedTimer = null;
let fedLoading = false;

const fmtRange = (lo, hi) => `${lo.toFixed(2)}–${hi.toFixed(2)}%`;

function fedWhen(iso, timeZone) {
  return new Date(iso).toLocaleString(undefined, {
    timeZone, weekday: "short", day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function moveLabel(bp) {
  if (bp === 0) return "No change";
  return bp > 0 ? `+${bp} bp hike` : `−${-bp} bp cut`;
}

function meetingDay(iso) {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

async function mountFedWatch(force = false) {
  startFedCountdown();
  if (!force && fedData && Date.now() - fedLoadedAt < FEDWATCH_REFRESH_MS) { renderFedWatch(); return; }
  if (fedLoading) return;
  fedLoading = true;
  const status = $("#fw-status");
  if (!fedData) { status.hidden = false; status.textContent = "Loading the FOMC calendar and futures prices…"; }
  try {
    fedData = await api("/api/fedwatch");
    fedLoadedAt = Date.now();
    renderFedWatch();
  } catch (e) {
    status.hidden = false;
    status.textContent = "Couldn't load FedWatch: " + e.message;
  } finally {
    fedLoading = false;
  }
}

function renderFedWatch() {
  const d = fedData;
  $("#fw-cme").href = d.cme_url;
  const problems = Object.values(d.errors || {});
  $("#fw-status").hidden = !problems.length;
  $("#fw-status").textContent = problems.length ? `Some data is missing: ${problems.join("; ")}.` : "";

  const next = d.next;
  $("#fw-next").hidden = !next;
  if (next) {
    $("#fw-when").textContent = `${fedWhen(next.decision, "America/New_York")} ET`;
    $("#fw-local").textContent = `Your time: ${fedWhen(next.decision)}` + (next.sep ? " · with new projections (dot plot)" : "");
  }
  tickFedCountdown();
  renderFedOdds(d);
  $("#fw-upcoming").replaceChildren(...(d.upcoming || []).map((m) =>
    el("li", null, meetingDay(m.date) + (m.sep ? " *" : ""))));
  $("#fw-upcoming-box").hidden = !(d.upcoming || []).length;
  $("#fw-sep-note").hidden = !(d.upcoming || []).some((m) => m.sep);   // the Fed marks them only when set
}

function renderFedOdds(d) {
  const box = $("#fw-odds");
  box.hidden = !d.odds;
  if (!d.odds) return;
  const t = d.target, o = d.odds;
  $("#fw-odds-title").textContent = `Target rate odds for ${meetingDay(o.meeting)}`;
  $("#fw-current").textContent = `Today's target range: ${fmtRange(t.low, t.high)} (effective rate ${t.effr.toFixed(2)}% on ${meetingDay(t.as_of)})`;
  const top = Math.max(...o.outcomes.map((x) => x.prob));
  $("#fw-bars").replaceChildren(...o.outcomes.map((x) => {
    const pct = (x.prob * 100).toFixed(1) + "%";
    const row = el("div", "fw-row" + (x.prob === top ? " top" : ""));
    row.title = `${fmtRange(x.low, x.high)} after the meeting (${moveLabel(x.move_bp).toLowerCase()}): ${pct}`;
    const fill = el("span", "fw-fill");
    fill.style.width = `${Math.max(x.prob * 100, 0.5)}%`;
    const track = el("span", "fw-track");
    track.append(fill);
    row.append(el("span", "fw-range", fmtRange(x.low, x.high)), el("span", "fw-move", moveLabel(x.move_bp)),
      track, el("span", "fw-prob", pct));
    return row;
  }));
  $("#fw-implied").textContent = `Implied average rate: ${o.rate_before.toFixed(2)}% before the meeting, `
    + `${o.rate_after.toFixed(2)}% after (anchored on the ${o.anchor}'s contract).`;
  $("#fw-contracts").textContent = o.contracts.map((c) =>
    `${c.symbol} ${c.price.toFixed(3)} (${timeAgo(c.time)})`).join(" · ");
}

// ---- countdown: ticks every second while the page is on screen ----
function startFedCountdown() {
  if (!fedTimer) fedTimer = setInterval(tickFedCountdown, 1000);
}

function tickFedCountdown() {
  if ($("#fedwatch").hidden) { clearInterval(fedTimer); fedTimer = null; return; }
  const next = fedData && fedData.next;
  const box = $("#fw-countdown");
  if (!next) { box.replaceChildren(); return; }
  const left = new Date(next.decision) - Date.now();
  if (left <= 0) {
    box.replaceChildren(el("span", "fw-due", "Decision due now"));
    if (Date.now() - fedLoadedAt > 60000) mountFedWatch(true);   // fetch the next meeting
    return;
  }
  const s = Math.floor(left / 1000);
  const parts = [[Math.floor(s / 86400), "days"], [Math.floor(s / 3600) % 24, "hours"],
    [Math.floor(s / 60) % 60, "min"], [s % 60, "sec"]];
  box.replaceChildren(...parts.map(([n, unit]) => {
    const cell = el("span", "fw-cell");
    cell.append(el("strong", null, String(n).padStart(2, "0")), el("span", null, unit));
    return cell;
  }));
  box.setAttribute("aria-label", `${parts[0][0]} days, ${parts[1][0]} hours and ${parts[2][0]} minutes to the decision`);
}
