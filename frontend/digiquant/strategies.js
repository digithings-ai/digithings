/**
 * strategies.js — render the strategy-tearsheet library index.
 *
 * Fetches ./strategies/index.json (the manifest emitted by make_tearsheets) and
 * renders one card per published strategy, linking to its tearsheet. Light/dark
 * + nav via the shared design foundation.
 */
import { initTheme } from "../design/site/theme.js";
import { initNav } from "../design/site/ui.js";
import { fmtCompact } from "./tearsheet-charts.js";

const $ = (s, r) => (r || document).querySelector(s);

function fmtPct(v) {
  if (v === null || v === undefined) return "n/a";
  if (Math.abs(v) >= 10000) return fmtCompact(v) + "%";
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "%";
}
function fmtNum(v, d) {
  if (v === null || v === undefined) return "n/a";
  return v.toLocaleString("en-US", { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 });
}
function tone(v) { return v > 0 ? "is-pos" : v < 0 ? "is-neg" : ""; }
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function kpi(label, valueHtml) {
  return `<div class="ts-card-kpi"><span class="ts-card-kpi-label">${esc(label)}</span>` +
    `<span class="ts-card-kpi-value">${valueHtml}</span></div>`;
}

function card(e) {
  const href = esc(e.href || `./tearsheet.html?s=${e.strategy}`);
  return (
    `<a class="ts-card" href="${href}">` +
    `<div class="ts-card-head"><span class="ts-card-name">${esc(e.strategy)}</span>` +
    `<span class="ts-chip">${esc(e.symbol)}</span></div>` +
    `<div class="ts-card-period">${esc(e.period_start)} → ${esc(e.period_end)}</div>` +
    `<div class="ts-card-kpis">` +
    kpi("Net profit", `<span class="${tone(e.net_profit_pct)}">${fmtPct(e.net_profit_pct)}</span>`) +
    kpi("Max DD", `<span class="is-neg">${fmtPct(e.max_drawdown_pct)}</span>`) +
    kpi("Profit factor", fmtNum(e.profit_factor, 2)) +
    kpi("Win rate", fmtPct(e.win_rate_pct)) +
    kpi("Trades", fmtNum(e.total_trades)) +
    `</div>` +
    `<span class="ts-card-cta">View tearsheet →</span>` +
    `</a>`
  );
}

function boot() {
  initTheme();
  initNav();
  fetch("./strategies/index.json")
    .then((r) => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); })
    .then((items) => {
      if (!Array.isArray(items) || items.length === 0) {
        $("#ts-lib").innerHTML = `<p class="ts-status">No published strategies yet.</p>`;
        return;
      }
      $("#ts-lib").innerHTML = items.map(card).join("");
    })
    .catch((e) => {
      $("#ts-lib").innerHTML =
        `<p class="ts-status ts-status-error">Could not load the strategy index (${e.message}).</p>`;
    });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
