/**
 * Dependency-free SVG charts for strategy tearsheets (React port of the
 * standalone renderer). Pure vector output (no canvas, no libs) so the tearsheet
 * prints to PDF crisply. Charts render into a 0 0 1000 H viewBox and scale to the
 * container width. Colours come from CSS custom properties on the chart classes
 * (theme-aware via [data-theme]). Supports linear / log / symlog y scales —
 * symlog handles series that cross zero (cumulative P&L).
 */
import { type ReactNode } from "react";
import { fmtCompact } from "./format";
import { type TearsheetPoint } from "./types";

const W = 1000;
const PAD = { top: 18, right: 26, bottom: 36, left: 84 };

export type Scale = "linear" | "log" | "symlog";
export type Tone = "accent" | "up" | "down";

function makeScale(kind: Scale) {
  if (kind === "log") {
    return { f: (v: number) => Math.log10(Math.max(v, 1e-9)), inv: (y: number) => Math.pow(10, y) };
  }
  if (kind === "symlog") {
    return {
      f: (v: number) => Math.sign(v) * Math.log10(1 + Math.abs(v)),
      inv: (y: number) => Math.sign(y) * (Math.pow(10, Math.abs(y)) - 1),
    };
  }
  return { f: (v: number) => v, inv: (y: number) => y };
}

function niceLinearTicks(min: number, max: number, count: number): number[] {
  if (min === max) return [min];
  const span = max - min;
  const step0 = Math.pow(10, Math.floor(Math.log10(span / count)));
  const e = span / count / step0;
  const step = e >= 7.5 ? step0 * 10 : e >= 3 ? step0 * 5 : e >= 1.5 ? step0 * 2 : step0;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 0.5; v += step) out.push(v);
  return out;
}

// Decade ticks for log/symlog, in real (untransformed) space.
function decadeTicks(kind: Scale, realLo: number, realHi: number): number[] {
  const ticks: number[] = [];
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

function Svg({ height, children }: { height: number; children: ReactNode }) {
  return (
    <svg
      viewBox={`0 0 ${W} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      className="ts-svg"
      role="img"
    >
      {children}
    </svg>
  );
}

function Empty({ height, msg }: { height: number; msg: string }) {
  return (
    <Svg height={height}>
      <text x={W / 2} y={height / 2} textAnchor="middle" className="ts-svg-empty">
        {msg}
      </text>
    </Svg>
  );
}

export interface TimeSeriesProps {
  points: TearsheetPoint[];
  height?: number;
  scale?: Scale;
  tone?: Tone;
  fmt?: (v: number) => string;
  zeroBaseline?: boolean;
}

/** Time-series area/line chart. */
export function TimeSeries({ points, height = 320, scale: scaleKind = "linear", tone = "accent", fmt = fmtCompact, zeroBaseline = false }: TimeSeriesProps) {
  if (!points || points.length === 0) return <Empty height={height} msg="no data" />;

  const scale = makeScale(scaleKind);
  const plotW = W - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;

  let lo = Infinity, hi = -Infinity;
  for (const p of points) {
    const y = scale.f(p.v);
    if (y < lo) lo = y;
    if (y > hi) hi = y;
  }
  if (zeroBaseline) {
    lo = Math.min(lo, scale.f(0));
    hi = Math.max(hi, scale.f(0));
  }
  if (lo === hi) hi = lo + 1;
  const padF = (hi - lo) * 0.07;
  lo -= padF;
  hi += padF;

  const n = points.length;
  const xAt = (i: number) => PAD.left + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const yAt = (val: number) => PAD.top + plotH - ((scale.f(val) - lo) / (hi - lo)) * plotH;

  const realLo = scale.inv(lo), realHi = scale.inv(hi);
  const ticks =
    scaleKind === "log" || scaleKind === "symlog"
      ? decadeTicks(scaleKind, realLo, realHi)
      : niceLinearTicks(realLo, realHi, 4);

  const gridEls: ReactNode[] = [];
  ticks.forEach((tv, i) => {
    const y = yAt(tv);
    if (y < PAD.top - 1 || y > PAD.top + plotH + 1) return;
    gridEls.push(
      <line key={`g${i}`} x1={PAD.left} y1={y} x2={W - PAD.right} y2={y} className={"ts-grid" + (tv === 0 ? " ts-grid-zero" : "")} />,
      <text key={`gt${i}`} x={PAD.left - 12} y={y + 5} textAnchor="end" className="ts-axis">{fmt(tv)}</text>,
    );
  });

  let line = "";
  for (let i = 0; i < n; i++) {
    line += (i ? "L" : "M") + xAt(i).toFixed(1) + " " + yAt(points[i].v).toFixed(1) + " ";
  }
  const baseReal = zeroBaseline ? 0 : realLo;
  const baseY = yAt(baseReal);
  const area = line + `L${xAt(n - 1).toFixed(1)} ${baseY.toFixed(1)} L${xAt(0).toFixed(1)} ${baseY.toFixed(1)} Z`;

  const idxs = [0, Math.floor((n - 1) / 2), n - 1];

  return (
    <Svg height={height}>
      {gridEls}
      <path d={area} className={"ts-area ts-tone-" + tone} />
      <path d={line} className={"ts-line ts-tone-" + tone} fill="none" />
      {idxs.map((i, k) => {
        const anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
        return (
          <text key={`x${k}`} x={xAt(i)} y={height - 10} textAnchor={anchor} className="ts-axis">
            {(points[i].t || "").slice(0, 10)}
          </text>
        );
      })}
    </Svg>
  );
}

export interface SignedBarsProps {
  values: number[];
  height?: number;
  fmt?: (v: number) => string;
}

/** Per-item signed bar chart (gains var(--up), losses var(--down)). */
export function SignedBars({ values, height = 220, fmt = fmtCompact }: SignedBarsProps) {
  if (!values || values.length === 0) return <Empty height={height} msg="no trades" />;

  const plotW = W - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;
  let lo = 0, hi = 0;
  for (const v of values) {
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (lo === hi) hi = lo + 1;
  const padF = (hi - lo) * 0.08;
  lo -= padF;
  hi += padF;

  const yAt = (v: number) => PAD.top + plotH - ((v - lo) / (hi - lo)) * plotH;
  const zeroY = yAt(0);

  const gridEls: ReactNode[] = [];
  niceLinearTicks(lo, hi, 4).forEach((tv, i) => {
    const y = yAt(tv);
    gridEls.push(
      <line key={`g${i}`} x1={PAD.left} y1={y} x2={W - PAD.right} y2={y} className={"ts-grid" + (tv === 0 ? " ts-grid-zero" : "")} />,
      <text key={`gt${i}`} x={PAD.left - 12} y={y + 5} textAnchor="end" className="ts-axis">{fmt(tv)}</text>,
    );
  });

  const n = values.length;
  const slot = plotW / n;
  const bw = Math.max(0.6, Math.min(slot * 0.7, 16));

  return (
    <Svg height={height}>
      {gridEls}
      {values.map((v, i) => {
        const x = PAD.left + i * slot + (slot - bw) / 2;
        const y = v >= 0 ? yAt(v) : zeroY;
        const h = Math.max(0.5, Math.abs(yAt(v) - zeroY));
        return (
          <rect key={i} x={x.toFixed(1)} y={y.toFixed(1)} width={bw.toFixed(1)} height={h.toFixed(1)} className={"ts-bar ts-tone-" + (v >= 0 ? "up" : "down")} />
        );
      })}
    </Svg>
  );
}

/** Scale for the cumulative line in ComboPnl: log dollars (symlog under the hood,
 * so the zero start and early negative crossings stay finite) or % of initial. */
export type PnlScale = "log" | "pct";

export interface ComboPnlProps {
  /** Per-trade P&L in dollars (left axis bars). */
  pnl: number[];
  /** Running cumulative P&L points (right axis line); same length / order as pnl. */
  cumulative: TearsheetPoint[];
  initialCapital: number;
  scale: PnlScale;
  height?: number;
}

/**
 * Dual-axis combo: per-trade P&L bars on the LEFT scale (gains up / losses down),
 * cumulative P&L as a line on its own RIGHT scale. The right scale toggles between
 * log dollars (symlog — legible across the strategy's many decades of compounding)
 * and cumulative return as a % of initial capital. Only the left/bars axis draws
 * gridlines; the right axis contributes labels only.
 */
export function ComboPnl({ pnl, cumulative, initialCapital, scale, height = 300 }: ComboPnlProps) {
  if (!pnl || pnl.length === 0) return <Empty height={height} msg="no trades" />;

  // Wider right gutter than the shared PAD.right (26): this is the only chart with
  // right-axis labels, and they ("100K", "80000%") need room to sit inside the
  // 1000-wide viewBox. Local to ComboPnl so the other charts are untouched.
  const PR = 60;
  const plotW = W - PAD.left - PR;
  const plotH = height - PAD.top - PAD.bottom;
  const n = pnl.length;
  const slot = plotW / n;
  const bw = Math.max(0.6, Math.min(slot * 0.7, 16));
  // Shared x: centre-of-slot, so trade i's bar and its cumulative point align.
  const xCenter = (i: number) => PAD.left + (i + 0.5) * slot;

  // ---- Left axis: per-trade P&L (linear, zero-anchored). Owns the gridlines. ----
  let lLo = 0, lHi = 0;
  for (const v of pnl) {
    if (v < lLo) lLo = v;
    if (v > lHi) lHi = v;
  }
  if (lLo === lHi) lHi = lLo + 1;
  const lPad = (lHi - lLo) * 0.08;
  lLo -= lPad;
  lHi += lPad;
  const yLeft = (v: number) => PAD.top + plotH - ((v - lLo) / (lHi - lLo)) * plotH;
  const zeroY = yLeft(0);

  const gridEls: ReactNode[] = [];
  niceLinearTicks(lLo, lHi, 4).forEach((tv, i) => {
    const y = yLeft(tv);
    gridEls.push(
      <line key={`g${i}`} x1={PAD.left} y1={y} x2={W - PR} y2={y} className={"ts-grid" + (tv === 0 ? " ts-grid-zero" : "")} />,
      <text key={`gt${i}`} x={PAD.left - 12} y={y + 5} textAnchor="end" className="ts-axis">{fmtCompact(tv)}</text>,
    );
  });

  // ---- Right axis: cumulative line. symlog for "log", linear % for "pct". ----
  const pct = scale === "pct";
  const cumScale = makeScale("symlog");
  // Project a cumulative dollar value to the plotted right-axis quantity.
  const project = (v: number) => (pct ? (v / initialCapital) * 100 : v);
  const rScaleF = (v: number) => (pct ? project(v) : cumScale.f(v));

  let rLo = Infinity, rHi = -Infinity;
  for (const p of cumulative) {
    const y = rScaleF(p.v);
    if (y < rLo) rLo = y;
    if (y > rHi) rHi = y;
  }
  // Anchor the right axis at zero too, so the line's baseline reads sensibly.
  rLo = Math.min(rLo, rScaleF(0));
  rHi = Math.max(rHi, rScaleF(0));
  if (rLo === rHi) rHi = rLo + 1;
  const rPad = (rHi - rLo) * 0.07;
  rLo -= rPad;
  rHi += rPad;
  const yRight = (v: number) => PAD.top + plotH - ((rScaleF(v) - rLo) / (rHi - rLo)) * plotH;

  // Right-axis ticks as {plotted-position, label} pairs. For log we format each
  // tick from its REAL dollar value (not a round-trip through symlog, which lands
  // 10^6 just under 1e6 → "1000K"); decadeTicks gives clean decades → "1M".
  let rTicks: { tp: number; label: string }[];
  if (pct) {
    // Compact the % labels (fmtCompact → "20K%", "10M%") so the flagship
    // strategies' multi-thousand-percent returns stay inside the viewBox — a
    // raw toFixed(0) emits "20000000%" (9 chars) and overflows the right edge.
    rTicks = niceLinearTicks(rLo, rHi, 4).map((tv) => ({ tp: tv, label: fmtCompact(tv) + "%" }));
  } else {
    const realLo = cumScale.inv(rLo), realHi = cumScale.inv(rHi);
    rTicks = decadeTicks("symlog", realLo, realHi).map((rv) => ({ tp: cumScale.f(rv), label: fmtCompact(rv) }));
  }
  const rightLabels: ReactNode[] = [];
  rTicks.forEach(({ tp, label }, i) => {
    const y = PAD.top + plotH - ((tp - rLo) / (rHi - rLo)) * plotH;
    if (y < PAD.top - 1 || y > PAD.top + plotH + 1) return;
    rightLabels.push(
      <text key={`r${i}`} x={W - PR + 12} y={y + 5} textAnchor="start" className="ts-axis">{label}</text>,
    );
  });

  // Cumulative line path (right axis), stroked only — no area, so bars stay visible.
  let line = "";
  for (let i = 0; i < n; i++) {
    const v = cumulative[i] ? cumulative[i].v : 0;
    line += (i ? "L" : "M") + xCenter(i).toFixed(1) + " " + yRight(v).toFixed(1) + " ";
  }

  // X date labels: first / mid / last trade exit, like TimeSeries.
  const idxs = [0, Math.floor((n - 1) / 2), n - 1];

  // Legend swatches (reuse existing classes only).
  const legY = PAD.top - 4;

  return (
    <Svg height={height}>
      {gridEls}
      {pnl.map((v, i) => {
        const x = PAD.left + i * slot + (slot - bw) / 2;
        const y = v >= 0 ? yLeft(v) : zeroY;
        const h = Math.max(0.5, Math.abs(yLeft(v) - zeroY));
        return (
          <rect key={i} x={x.toFixed(1)} y={y.toFixed(1)} width={bw.toFixed(1)} height={h.toFixed(1)} className={"ts-bar ts-tone-" + (v >= 0 ? "up" : "down")} />
        );
      })}
      <path d={line} className="ts-line ts-tone-accent" fill="none" />
      {rightLabels}
      {idxs.map((i, k) => {
        const anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
        const pt = cumulative[i];
        return (
          <text key={`x${k}`} x={xCenter(i)} y={height - 10} textAnchor={anchor} className="ts-axis">
            {(pt && pt.t ? pt.t : "").slice(0, 10)}
          </text>
        );
      })}
      {/* Legend — which series maps to which axis. */}
      <rect x={PAD.left} y={legY - 9} width={14} height={9} className="ts-bar ts-tone-up" />
      <text x={PAD.left + 20} y={legY} textAnchor="start" className="ts-axis">per-trade P&amp;L (L)</text>
      <line x1={PAD.left + 200} y1={legY - 4} x2={PAD.left + 232} y2={legY - 4} className="ts-line ts-tone-accent" />
      <text x={PAD.left + 238} y={legY} textAnchor="start" className="ts-axis">cumulative (R)</text>
    </Svg>
  );
}
