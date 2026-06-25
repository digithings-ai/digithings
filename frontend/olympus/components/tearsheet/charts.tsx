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
