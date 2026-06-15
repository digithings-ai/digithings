/**
 * tearsheet-charts.js — dependency-free SVG charts for strategy tearsheets.
 *
 * Pure vector output (no canvas, no libs) so the tearsheet embeds anywhere and
 * prints to PDF crisply. Charts render into a 0 0 1000 H viewBox and scale to
 * the container width. Colours come from CSS custom properties on the chart
 * classes (theme-aware via [data-theme]). Supports linear / log / symlog y
 * scales — symlog handles series that cross zero (cumulative P&L).
 */

const NS = "http://www.w3.org/2000/svg";
const W = 1000;
const PAD = { top: 18, right: 26, bottom: 36, left: 84 };

function el(name, attrs, parent) {
  const node = document.createElementNS(NS, name);
  for (const k in attrs) node.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(node);
  return node;
}

export function fmtCompact(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "";
  const a = Math.abs(v);
  if (a >= 1e9) return (v / 1e9).toFixed(a >= 1e10 ? 0 : 1) + "B";
  if (a >= 1e6) return (v / 1e6).toFixed(a >= 1e7 ? 0 : 1) + "M";
  if (a >= 1e3) return (v / 1e3).toFixed(a >= 1e4 ? 0 : 1) + "K";
  if (a >= 1) return v.toFixed(0);
  if (a === 0) return "0";
  return v.toFixed(2);
}

// ── scale transforms ──────────────────────────────────────────────────────
function makeScale(kind) {
  if (kind === "log") {
    return { f: (v) => Math.log10(Math.max(v, 1e-9)), inv: (y) => Math.pow(10, y) };
  }
  if (kind === "symlog") {
    const f = (v) => Math.sign(v) * Math.log10(1 + Math.abs(v));
    const inv = (y) => Math.sign(y) * (Math.pow(10, Math.abs(y)) - 1);
    return { f, inv };
  }
  return { f: (v) => v, inv: (y) => y };
}

function niceLinearTicks(min, max, count) {
  if (min === max) return [min];
  const span = max - min;
  const step0 = Math.pow(10, Math.floor(Math.log10(span / count)));
  const e = span / count / step0;
  const step = e >= 7.5 ? step0 * 10 : e >= 3 ? step0 * 5 : e >= 1.5 ? step0 * 2 : step0;
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 0.5; v += step) out.push(v);
  return out;
}

// Decade ticks for log/symlog, in real (untransformed) space.
function decadeTicks(kind, realLo, realHi) {
  const ticks = [];
  const maxAbs = Math.max(Math.abs(realLo), Math.abs(realHi));
  if (maxAbs <= 0) return [0];
  const topK = Math.ceil(Math.log10(maxAbs));
  if (kind === "symlog") {
    ticks.push(0);
    for (let k = 1; k <= topK; k++) {
      const v = Math.pow(10, k);
      if (v <= realHi) ticks.push(v);
      if (-v >= realLo) ticks.push(-v);
    }
  } else {
    const botK = Math.floor(Math.log10(Math.max(realLo, 1e-9)));
    for (let k = botK; k <= topK; k++) {
      const v = Math.pow(10, k);
      if (v >= realLo * 0.999 && v <= realHi * 1.001) ticks.push(v);
    }
  }
  return ticks.length ? ticks : [realLo, realHi];
}

function makeSvg(host, height) {
  host.innerHTML = "";
  return el("svg", {
    viewBox: `0 0 ${W} ${height}`,
    preserveAspectRatio: "xMidYMid meet",
    class: "ts-svg",
    role: "img",
  }, host);
}

function emptyState(svg, height, msg) {
  el("text", { x: W / 2, y: height / 2, "text-anchor": "middle", class: "ts-svg-empty" }, svg)
    .textContent = msg;
}

/**
 * Time-series area/line chart.
 * @param host    container element
 * @param points  [{t, v}, ...]
 * @param opts    { height, scale:'linear'|'log'|'symlog', tone:'accent'|'up'|'down',
 *                  fmt(v), zeroBaseline:bool }
 */
export function timeSeries(host, points, opts = {}) {
  const height = opts.height || 320;
  const svg = makeSvg(host, height);
  if (!points || points.length === 0) return emptyState(svg, height, "no data");

  const scale = makeScale(opts.scale || "linear");
  const fmt = opts.fmt || fmtCompact;
  const tone = opts.tone || "accent";
  const plotW = W - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;

  let lo = Infinity, hi = -Infinity;
  for (const p of points) { const y = scale.f(p.v); if (y < lo) lo = y; if (y > hi) hi = y; }
  if (opts.zeroBaseline) { lo = Math.min(lo, scale.f(0)); hi = Math.max(hi, scale.f(0)); }
  if (lo === hi) hi = lo + 1;
  const padF = (hi - lo) * 0.07;
  lo -= padF; hi += padF;

  const n = points.length;
  const xAt = (i) => PAD.left + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const yAt = (val) => PAD.top + plotH - ((scale.f(val) - lo) / (hi - lo)) * plotH;

  // gridlines + y labels
  const realLo = scale.inv(lo), realHi = scale.inv(hi);
  const ticks = (opts.scale === "log" || opts.scale === "symlog")
    ? decadeTicks(opts.scale, realLo, realHi)
    : niceLinearTicks(realLo, realHi, 4);
  for (const tv of ticks) {
    const y = yAt(tv);
    if (y < PAD.top - 1 || y > PAD.top + plotH + 1) continue;
    el("line", { x1: PAD.left, y1: y, x2: W - PAD.right, y2: y,
      class: "ts-grid" + (tv === 0 ? " ts-grid-zero" : "") }, svg);
    el("text", { x: PAD.left - 12, y: y + 5, "text-anchor": "end", class: "ts-axis" }, svg)
      .textContent = fmt(tv);
  }

  // area + line
  let line = "";
  for (let i = 0; i < n; i++) {
    line += (i ? "L" : "M") + xAt(i).toFixed(1) + " " + yAt(points[i].v).toFixed(1) + " ";
  }
  const baseReal = opts.zeroBaseline ? 0 : realLo;
  const baseY = yAt(baseReal);
  const area = line + `L${xAt(n - 1).toFixed(1)} ${baseY.toFixed(1)} L${xAt(0).toFixed(1)} ${baseY.toFixed(1)} Z`;
  el("path", { d: area, class: "ts-area ts-tone-" + tone }, svg);
  el("path", { d: line, class: "ts-line ts-tone-" + tone, fill: "none" }, svg);

  // x labels (first / mid / last)
  const idxs = [0, Math.floor((n - 1) / 2), n - 1];
  for (const i of idxs) {
    const anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
    el("text", { x: xAt(i), y: height - 10, "text-anchor": anchor, class: "ts-axis" }, svg)
      .textContent = (points[i].t || "").slice(0, 10);
  }
}

/**
 * Per-item signed bar chart (gains var(--up), losses var(--down)).
 * @param host    container element
 * @param values  [number, ...]
 * @param opts    { height, fmt(v) }
 */
export function signedBars(host, values, opts = {}) {
  const height = opts.height || 220;
  const svg = makeSvg(host, height);
  if (!values || values.length === 0) return emptyState(svg, height, "no trades");

  const fmt = opts.fmt || fmtCompact;
  const plotW = W - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  let lo = 0, hi = 0;
  for (const v of values) { if (v < lo) lo = v; if (v > hi) hi = v; }
  if (lo === hi) hi = lo + 1;
  const padF = (hi - lo) * 0.08;
  lo -= padF; hi += padF;

  const yAt = (v) => PAD.top + plotH - ((v - lo) / (hi - lo)) * plotH;
  const zeroY = yAt(0);
  for (const tv of niceLinearTicks(lo, hi, 4)) {
    const y = yAt(tv);
    el("line", { x1: PAD.left, y1: y, x2: W - PAD.right, y2: y,
      class: "ts-grid" + (tv === 0 ? " ts-grid-zero" : "") }, svg);
    el("text", { x: PAD.left - 12, y: y + 5, "text-anchor": "end", class: "ts-axis" }, svg)
      .textContent = fmt(tv);
  }

  const n = values.length;
  const slot = plotW / n;
  const bw = Math.max(0.6, Math.min(slot * 0.7, 16));
  for (let i = 0; i < n; i++) {
    const v = values[i];
    const x = PAD.left + i * slot + (slot - bw) / 2;
    const y = v >= 0 ? yAt(v) : zeroY;
    const h = Math.max(0.5, Math.abs(yAt(v) - zeroY));
    el("rect", { x: x.toFixed(1), y: y.toFixed(1), width: bw.toFixed(1), height: h.toFixed(1),
      class: "ts-bar ts-tone-" + (v >= 0 ? "up" : "down") }, svg);
  }
}
