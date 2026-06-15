/**
 * tearsheet.js — render a strategy tearsheet from unified TearsheetData JSON.
 *
 * Reads ?s=<strategy> (or ?src=<url>), fetches the JSON emitted by
 * digiquant.tearsheet_data, and renders KPIs, breakdown tables, theme-aware SVG
 * charts, and the trade log. Light/dark via the shared design toggle;
 * "Download PDF" uses the browser's print-to-PDF (full-bleed, theme-matched).
 */
import { initTheme } from "../design/site/theme.js";
import { initNav } from "../design/site/ui.js";
import { timeSeries, signedBars, fmtCompact } from "./tearsheet-charts.js";

const $ = (sel, root) => (root || document).querySelector(sel);

function param(name) {
  return new URLSearchParams(window.location.search).get(name);
}

// Compact above a threshold so huge compounded figures never overflow a card.
function fmtPct(v) {
  if (v === null || v === undefined) return "n/a";
  if (Math.abs(v) >= 10000) return fmtCompact(v) + "%";
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "%";
}
function fmtMoney(v) {
  if (v === null || v === undefined) return "n/a";
  if (Math.abs(v) >= 100000) return fmtCompact(v);
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtNum(v, d) {
  if (v === null || v === undefined) return "n/a";
  return v.toLocaleString("en-US", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 });
}
function toneClass(v) {
  return v > 0 ? "is-pos" : v < 0 ? "is-neg" : "";
}
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function kpi(label, valueHtml, sub) {
  return (
    `<div class="ts-kpi">` +
    `<span class="ts-kpi-label">${esc(label)}</span>` +
    `<span class="ts-kpi-value">${valueHtml}</span>` +
    (sub ? `<span class="ts-kpi-sub">${esc(sub)}</span>` : "") +
    `</div>`
  );
}

function renderHeader(d) {
  $("#ts-title").textContent = d.strategy;
  $("#ts-meta").innerHTML =
    `<span class="ts-chip">${esc(d.symbol)}</span>` +
    `<span class="ts-chip ts-chip-soft">${esc(d.engine)} engine</span>` +
    `<span class="ts-meta-text">${esc(d.period_start)} → ${esc(d.period_end)} · ` +
    `${fmtNum(d.bars)} bars</span>`;
  document.title = `${d.strategy} · ${d.symbol} — DigiQuant tearsheet`;
}

function renderKpis(d) {
  const kpis = [
    kpi("Net profit", `<span class="${toneClass(d.net_profit_pct)}">${fmtPct(d.net_profit_pct)}</span>`,
      `${fmtMoney(d.initial_capital)} → ${fmtMoney(d.final_equity)}`),
    kpi("Max drawdown", `<span class="is-neg">${fmtPct(d.max_drawdown_pct)}</span>`, "mark-to-market"),
    kpi("Profit factor", fmtNum(d.profit_factor, 2), "gross win / gross loss"),
    kpi("Win rate", fmtPct(d.win_rate_pct), `${d.total_trades} trades`),
    kpi("Avg trade", `<span class="${toneClass(d.avg_trade)}">${fmtMoney(d.avg_trade)}</span>`, "per closed trade"),
  ];
  if (d.sharpe_ratio !== null && d.sharpe_ratio !== undefined) {
    kpis.push(kpi("Sharpe", fmtNum(d.sharpe_ratio, 2), "annualized"));
  }
  $("#ts-kpis").innerHTML = kpis.join("");
}

function renderBreakdown(d) {
  const all = d.overall || {}, lo = d.long || {}, sh = d.short || {};
  const money = (b, k) => fmtMoney(b ? b[k] : null);
  const pct = (b, k) => fmtPct(b ? b[k] : null);
  const num = (b, k, dd) => fmtNum(b ? b[k] : null, dd);
  const signedMoney = (b, k) => {
    const v = b ? b[k] : null;
    return `<span class="${toneClass(v)}">${fmtMoney(v)}</span>`;
  };
  const row = (label, fn) =>
    `<tr><th scope="row">${esc(label)}</th><td>${fn(all)}</td><td>${fn(lo)}</td><td>${fn(sh)}</td></tr>`;
  $("#ts-breakdown").innerHTML =
    `<table class="ts-table ts-breakdown">` +
    `<thead><tr><th>Metric</th><th>All</th><th>Long</th><th>Short</th></tr></thead><tbody>` +
    row("Closed trades", (b) => num(b, "trades")) +
    row("Net profit", (b) => signedMoney(b, "net_profit")) +
    row("Net profit %", (b) => pct(b, "net_profit_pct")) +
    row("Gross profit", (b) => money(b, "gross_profit")) +
    row("Gross loss", (b) => money(b, "gross_loss")) +
    row("Percent profitable", (b) => pct(b, "percent_profitable")) +
    row("Profit factor", (b) => num(b, "profit_factor", 2)) +
    row("Avg trade", (b) => signedMoney(b, "avg_trade")) +
    `</tbody></table>`;
}

function renderCharts(d) {
  const scaleSel = $("#ts-equity-scale");
  const drawEquity = () => timeSeries($("#ts-chart-equity"), d.equity_curve, {
    height: 340, scale: scaleSel.value, tone: "accent", fmt: fmtCompact,
  });
  drawEquity();
  scaleSel.addEventListener("change", drawEquity);

  timeSeries($("#ts-chart-drawdown"), d.drawdown_curve, {
    height: 220, scale: "linear", tone: "down", zeroBaseline: true,
    fmt: (v) => v.toFixed(0) + "%",
  });

  const pnls = (d.trades || []).map((t) => t.pnl);
  signedBars($("#ts-chart-trade-pnl"), pnls, { height: 220, fmt: fmtCompact });

  // Cumulative P&L crosses zero early then compounds → symlog keeps both legible.
  let cum = 0;
  const cumPts = (d.trades || []).map((t) => { cum += t.pnl; return { t: t.exit_date, v: cum }; });
  timeSeries($("#ts-chart-cum-pnl"), cumPts, {
    height: 220, scale: "symlog", tone: "accent", zeroBaseline: true, fmt: fmtCompact,
  });
}

function renderTrades(d) {
  const rows = (d.trades || []).map((t) =>
    `<tr>` +
    `<td>${t.n}</td>` +
    `<td><span class="ts-dir ts-dir-${esc(t.direction)}">${esc(t.direction)}</span></td>` +
    `<td>${esc(t.entry_label)}</td>` +
    `<td>${esc(t.entry_date)}</td>` +
    `<td class="ts-num">${fmtMoney(t.entry_price)}</td>` +
    `<td>${esc(t.exit_date)}</td>` +
    `<td class="ts-num">${fmtMoney(t.exit_price)}</td>` +
    `<td class="ts-num ${toneClass(t.pnl)}">${fmtMoney(t.pnl)}</td>` +
    `<td class="ts-num ${toneClass(t.pnl_pct)}">${fmtPct(t.pnl_pct)}</td>` +
    `<td>${esc(t.exit_reason)}</td>` +
    `</tr>`).join("");
  $("#ts-trades").innerHTML =
    `<table class="ts-table ts-trades">` +
    `<thead><tr><th>#</th><th>Dir</th><th>Entry signal</th><th>Entry date</th>` +
    `<th class="ts-num">Entry px</th><th>Exit date</th><th class="ts-num">Exit px</th>` +
    `<th class="ts-num">P&amp;L</th><th class="ts-num">P&amp;L %</th><th>Exit</th></tr></thead>` +
    `<tbody>${rows}</tbody></table>`;
}

function renderNotes(d) {
  const notes = (d.notes || []).slice();
  if (d.data_source) notes.unshift(`Data source: ${d.data_source}`);
  if (d.generated_at) notes.push(`Generated ${d.generated_at}`);
  if (!notes.length) { $("#ts-notes").hidden = true; return; }
  $("#ts-notes").innerHTML = notes.map((n) => `<li>${esc(n)}</li>`).join("");
}

function render(d) {
  renderHeader(d);
  renderKpis(d);
  renderBreakdown(d);
  renderCharts(d);
  renderTrades(d);
  renderNotes(d);
  $("#ts-root").hidden = false;
  $("#ts-loading").hidden = true;
}

function fail(msg) {
  $("#ts-loading").hidden = true;
  const err = $("#ts-error");
  err.hidden = false;
  err.textContent = msg;
}

function boot() {
  initTheme();
  initNav();
  const printBtn = $("#ts-print");
  if (printBtn) printBtn.addEventListener("click", () => window.print());

  const slug = (param("s") || "btc_slapper").replace(/[^a-z0-9_-]/gi, "");
  const src = param("src") || `./strategies/${slug}.json`;
  fetch(src)
    .then((r) => { if (!r.ok) throw new Error(`${r.status} ${r.statusText}`); return r.json(); })
    .then(render)
    .catch((e) => fail(`Could not load tearsheet data (${src}): ${e.message}`));
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
