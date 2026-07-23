"use client";
/**
 * Dependency-free SVG charts for finance tearsheets (#1463) — promoted
 * verbatim from frontend/digiquant-web/components/tearsheet/charts.tsx.
 * Pure vector output (no canvas, no libs) so the tearsheet prints to PDF
 * crisply: the PDF pipeline flushSync-re-renders these same component
 * instances at full span and calls window.print(), so print-first pure-SVG
 * is a hard constraint here. Canvas engines are the DASHBOARD grammar
 * (finance-charts / finance-composites) — see frontend/digiweb/CHARTS.md
 * before swapping engines on any surface.
 *
 * Charts render into a 0 0 1000 H viewBox and scale to the container width.
 * Colours come from CSS custom properties on the chart classes (theme-aware
 * via [data-theme]). Supports linear / log / symlog y scales — symlog
 * handles series that cross zero (cumulative P&L). The series surfaces
 * (CandlestickChart, TimeSeries, TradeReturnChart) share one normalized
 * ViewWindow: wheel-zoom / drag-pan / double-click reset stay synced across
 * charts, with lookback presets matched back via `matchLookbackPreset`.
 */
import { type ReactNode, type RefObject, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { fmtCompact, fmtMoney, fmtNum, fmtPct, toneClass } from "./format";
import {
  isOpenTrade,
  type TearsheetOhlcBar,
  type TearsheetSeriesPoint,
  type TearsheetTrade,
  type TradeReturnBar,
} from "./types";

const W = 1000;
const PAD = { top: 30, right: 18, bottom: 34, left: 68 };
/** Tighter gutters for homepage preview cards — more plot area edge-to-edge. */
const PAD_COMPACT = { top: 16, right: 4, bottom: 22, left: 44 };

type ChartPad = typeof PAD;

function resolveChartPad(widthPx: number, compact: boolean): ChartPad {
  const base = compact ? PAD_COMPACT : PAD;
  if (widthPx >= 640) return { ...base };
  const t = Math.max(0, Math.min(1, (widthPx - 280) / (640 - 280)));
  return {
    top: compact ? base.top : Math.round(20 + t * (base.top - 20)),
    right: compact ? base.right : Math.round(6 + t * (base.right - 6)),
    bottom: compact ? base.bottom : Math.round(26 + t * (base.bottom - 26)),
    left: compact
      ? Math.round(26 + t * (base.left - 26))
      : Math.round(40 + t * (base.left - 40)),
  };
}

/** Match viewBox width to container aspect so fill-mode scaling stays uniform. */
function useChartLayout(
  wrapRef: RefObject<HTMLDivElement | null>,
  vbH: number,
  compact: boolean,
): { vbW: number; pad: ChartPad } {
  const [layout, setLayout] = useState<{ vbW: number; pad: ChartPad }>(() => ({
    vbW: W,
    pad: compact ? PAD_COMPACT : PAD,
  }));

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;

    const update = () => {
      const { width, height } = el.getBoundingClientRect();
      if (width <= 0 || height <= 0) return;
      const vbW = Math.max(280, Math.round((width / height) * vbH));
      setLayout({
        vbW,
        pad: resolveChartPad(width, compact),
      });
    };

    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [wrapRef, vbH, compact]);

  return layout;
}

/** Pointer position in viewBox coords. */
function viewBoxPoint(
  clientX: number,
  clientY: number,
  svg: Element,
  vbW: number,
  vbH: number,
): { x: number; y: number } {
  const rect = svg.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return { x: vbW / 2, y: vbH / 2 };
  return {
    x: ((clientX - rect.left) / rect.width) * vbW,
    y: ((clientY - rect.top) / rect.height) * vbH,
  };
}

interface ChartHoverTip {
  x: number;
  y: number;
  flipX: boolean;
  flipY: boolean;
  content: ReactNode;
}

function positionHoverTip(
  clientX: number,
  clientY: number,
  wrap: HTMLElement,
  estW = 200,
  estH = 96,
): Pick<ChartHoverTip, "x" | "y" | "flipX" | "flipY"> {
  const rect = wrap.getBoundingClientRect();
  const pad = 12;
  const relX = clientX - rect.left;
  const relY = clientY - rect.top;
  const flipX = relX + pad + estW > rect.width;
  const flipY = relY - pad - estH < 0;
  return {
    x: relX,
    y: relY,
    flipX,
    flipY,
  };
}

function ChartHoverShell({
  hover,
  children,
  wrapRef,
}: {
  hover: ChartHoverTip | null;
  children: ReactNode;
  wrapRef?: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div className="ts-chart-wrap" ref={wrapRef}>
      {children}
      {hover ? (
        <div
          className={
            "ts-chart-tip" +
            (hover.flipX ? " is-flip-x" : "") +
            (hover.flipY ? " is-flip-y" : "")
          }
          style={{ left: hover.x, top: hover.y }}
          role="tooltip"
        >
          {hover.content}
        </div>
      ) : null}
    </div>
  );
}

function TradeTipContent({ trade, showPnlMoney = false }: { trade: TearsheetTrade; showPnlMoney?: boolean }) {
  const open = isOpenTrade(trade);
  const pnlTone = toneClass(trade.pnl_pct);
  return (
    <div className="ts-chart-tip-body">
      <div className="ts-chart-tip-title">
        <span className={`ts-dir ts-dir-${trade.direction}`}>{trade.direction}</span>
        {trade.entry_label ? <span className="ts-chart-tip-signal">{trade.entry_label}</span> : null}
      </div>
      <dl className="ts-chart-tip-dl">
        <div>
          <dt>Entry</dt>
          <dd>
            {(trade.entry_date || "").slice(0, 10)} @ {fmtNum(trade.entry_price, 2)}
          </dd>
        </div>
        <div>
          <dt>Exit</dt>
          <dd>
            {open
              ? "open"
              : `${(trade.exit_date || "").slice(0, 10)} @ ${fmtNum(trade.exit_price, 2)}`}
          </dd>
        </div>
        <div>
          <dt>P&amp;L</dt>
          <dd className={pnlTone}>
            {fmtPct(trade.pnl_pct)}
            {showPnlMoney ? ` · ${fmtMoney(trade.pnl)}` : null}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function OhlcTipContent({ bar }: { bar: TearsheetOhlcBar }) {
  return (
    <dl className="ts-chart-tip-dl">
      <div>
        <dt>Date</dt>
        <dd>{(bar.t || "").slice(0, 10)}</dd>
      </div>
      <div>
        <dt>Open</dt>
        <dd>{fmtNum(bar.o, 2)}</dd>
      </div>
      <div>
        <dt>High</dt>
        <dd>{fmtNum(bar.h, 2)}</dd>
      </div>
      <div>
        <dt>Low</dt>
        <dd>{fmtNum(bar.l, 2)}</dd>
      </div>
      <div>
        <dt>Close</dt>
        <dd>{fmtNum(bar.c, 2)}</dd>
      </div>
    </dl>
  );
}

function SeriesTipContent({ date, value }: { date: string; value: string }) {
  return (
    <dl className="ts-chart-tip-dl">
      <div>
        <dt>Date</dt>
        <dd>{date.slice(0, 10)}</dd>
      </div>
      <div>
        <dt>Value</dt>
        <dd>{value}</dd>
      </div>
    </dl>
  );
}

function ContributionReturnTipContent({
  point,
  colors,
}: {
  point: ContributionReturnPoint;
  /** Per-series swatch colors — replaces a header legend, which does not scale past a handful of assets. */
  colors?: Record<string, string>;
}) {
  const contributions = Object.entries(point.contributions)
    .filter(([, value]) => value !== 0)
    .sort((left, right) => Math.abs(right[1]) - Math.abs(left[1]));
  return (
    <div className="ts-chart-tip-body">
      <dl className="ts-chart-tip-dl">
        <div><dt>Date</dt><dd>{point.t.slice(0, 10)}</dd></div>
        <div><dt>Portfolio</dt><dd>{fmtPct(point.returnPct)}</dd></div>
        {contributions.map(([label, value]) => (
          <div key={label}>
            <dt>
              {colors?.[label] ? (
                <span
                  aria-hidden="true"
                  style={{
                    display: "inline-block",
                    width: "0.55em",
                    height: "0.55em",
                    marginRight: "0.45em",
                    backgroundColor: colors[label],
                  }}
                />
              ) : null}
              {label}
            </dt>
            <dd>{fmtPct(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

interface MarkerHit {
  x: number;
  y: number;
  role: "entry" | "exit";
  trade: TearsheetTrade;
}

/** Nearest marker triangle; on reversal bars entry/exit share a bar — prefer entry. */
function hitMarker(vbX: number, vbY: number, markers: MarkerHit[], threshold = 20): MarkerHit | null {
  let best: MarkerHit | null = null;
  let bestD = threshold;
  for (const m of markers) {
    const d = Math.hypot(vbX - m.x, vbY - m.y);
    if (d > bestD) continue;
    if (
      d < bestD ||
      !best ||
      (m.role === "entry" && best.role === "exit")
    ) {
      bestD = d;
      best = m;
    }
  }
  return best;
}

function nearestBarIndex(vbX: number, n: number, xAt: (i: number) => number, maxDist: number): number {
  if (n <= 0) return -1;
  if (n === 1) return 0;
  let best = 0;
  let bestD = Infinity;
  for (let i = 0; i < n; i++) {
    const d = Math.abs(vbX - xAt(i));
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return bestD <= maxDist ? best : -1;
}

/** Default zoom: last calendar year of the shared span (readable on long backtests). */
export function viewWindowLastYear(fullSpan: [string, string] | undefined): ViewWindow {
  return viewWindowForPreset("1y", fullSpan);
}

export type LookbackPreset = "1m" | "3m" | "6m" | "ytd" | "1y" | "3y" | "all";

export const LOOKBACK_OPTIONS: { value: LookbackPreset; label: string }[] = [
  { value: "1m", label: "1M" },
  { value: "3m", label: "3M" },
  { value: "6m", label: "6M" },
  { value: "ytd", label: "YTD" },
  { value: "1y", label: "1Y" },
  { value: "3y", label: "3Y" },
  { value: "all", label: "All" },
];

const MS_DAY = 24 * 3600 * 1000;

function spanEndpoints(fullSpan: [string, string]): { t0: number; t1: number; spanMs: number } | null {
  const t0 = new Date(fullSpan[0]).getTime();
  const t1 = new Date(fullSpan[1]).getTime();
  const spanMs = t1 - t0;
  if (!Number.isFinite(spanMs) || spanMs <= 0) return null;
  return { t0, t1, spanMs };
}

/** Map a lookback preset to a normalized [lo, hi] window over `fullSpan`. */
export function viewWindowForPreset(
  preset: LookbackPreset,
  fullSpan: [string, string] | undefined,
): ViewWindow {
  if (!fullSpan || preset === "all") return { lo: 0, hi: 1 };
  const span = spanEndpoints(fullSpan);
  if (!span) return { lo: 0, hi: 1 };

  const { t0, t1, spanMs } = span;
  let startMs: number;
  switch (preset) {
    case "1m":
      startMs = t1 - 30 * MS_DAY;
      break;
    case "3m":
      startMs = t1 - 91.25 * MS_DAY;
      break;
    case "6m":
      startMs = t1 - 182.625 * MS_DAY;
      break;
    case "ytd": {
      const end = new Date(fullSpan[1]);
      startMs = Date.UTC(end.getUTCFullYear(), 0, 1);
      break;
    }
    case "1y":
      startMs = t1 - 365.25 * MS_DAY;
      break;
    case "3y":
      startMs = t1 - 3 * 365.25 * MS_DAY;
      break;
    default: {
      const _exhaustive: never = preset;
      return _exhaustive;
    }
  }
  const lo = Math.max(0, (startMs - t0) / spanMs);
  return clampView(lo, 1);
}

const VIEW_EPS = 0.002;

/** True when two normalized windows are effectively the same. */
export function viewsNear(a: ViewWindow, b: ViewWindow): boolean {
  return Math.abs(a.lo - b.lo) < VIEW_EPS && Math.abs(a.hi - b.hi) < VIEW_EPS;
}

/** Which preset matches this window, if any. */
export function matchLookbackPreset(
  view: ViewWindow,
  fullSpan: [string, string] | undefined,
): LookbackPreset | null {
  if (!fullSpan) return null;
  for (const { value } of LOOKBACK_OPTIONS) {
    if (viewsNear(view, viewWindowForPreset(value, fullSpan))) return value;
  }
  return null;
}

/** Tight y-domain in transformed scale space with optional zero anchor. */
function dataDomain(
  values: number[],
  scale: { f: (v: number) => number },
  opts: { padRatio?: number; anchorZero?: "min" | "max" },
): { lo: number; hi: number } {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of values) {
    const y = scale.f(v);
    if (y < lo) lo = y;
    if (y > hi) hi = y;
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return { lo: 0, hi: 1 };
  if (opts.anchorZero === "min") lo = Math.min(lo, scale.f(0));
  if (opts.anchorZero === "max") hi = Math.max(hi, scale.f(0));
  if (lo === hi) hi = lo + 1;
  const pad = (hi - lo) * (opts.padRatio ?? 0.05);
  return { lo: lo - pad, hi: hi + pad };
}

/** Compact HTML legend for panel headers (top-right, beside controls). */
export function ChartLegend({
  items,
}: {
  items: { kind: "line" | "bar-up" | "bar-down" | "bar-open" | "marker-buy" | "marker-sell"; label: string }[];
}) {
  return (
    <div className="ts-chart-legend" aria-hidden="true">
      {items.map((it) => (
        <span className="ts-chart-legend-item" key={it.label}>
          <span className={`ts-chart-legend-swatch ts-chart-legend-${it.kind}`} />
          <span>{it.label}</span>
        </span>
      ))}
    </div>
  );
}

function axisLabelY(y: number, plotTop: number, plotBottom: number): number {
  return Math.max(plotTop + 11, Math.min(plotBottom - 2, y + 4));
}

export type ChartScale = "linear" | "log" | "symlog";
export type ChartTone = "accent" | "up" | "down";

/** A normalized x-domain window (fractions 0..1 over a chart's full date span). */
export interface ViewWindow {
  lo: number;
  hi: number;
}
/** Smallest allowed window (2% of the span) — keeps zoom from collapsing. */
const MIN_VIEW = 0.02;

function clampView(lo: number, hi: number): ViewWindow {
  let l = Math.max(0, Math.min(lo, 1));
  let h = Math.max(0, Math.min(hi, 1));
  if (h - l < MIN_VIEW) {
    // Re-expand around the window centre, then re-clamp into [0,1].
    const mid = (l + h) / 2;
    l = Math.max(0, mid - MIN_VIEW / 2);
    h = Math.min(1, l + MIN_VIEW);
    l = Math.max(0, h - MIN_VIEW);
  }
  return { lo: l, hi: h };
}

/** Icon-only reset zoom — floats over the chart area (top-right). */
export function ChartResetButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className="ts-reset ts-reset-chart"
      onClick={onClick}
      aria-label="Reset zoom to selected time range"
    >
      <svg
        viewBox="0 0 24 24"
        width="15"
        height="15"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M8 3H5a2 2 0 0 0-2 2v3" />
        <path d="M16 3h3a2 2 0 0 1 2 2v3" />
        <path d="M8 21H5a2 2 0 0 1-2-2v-3" />
        <path d="M16 21h3a2 2 0 0 0 2-2v-3" />
      </svg>
    </button>
  );
}

/**
 * Generic segmented-button toggle. Real <button>s with aria-pressed inside a
 * labelled group — accessible, theme-aware (active = accent). Used for the equity
 * scale, the cumulative-P&L scale, and the returns-matrix period selector.
 */
export function SegToggle<T extends string>({
  value,
  options,
  onChange,
  label,
  className,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
  className?: string;
}) {
  return (
    <div className={"ts-seg" + (className ? ` ${className}` : "")} role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={"ts-seg-btn" + (o.value === value ? " is-active" : "")}
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/**
 * Translate a pointer event over the chart SVG into a fraction (0..1) across the
 * plot area (inside the left/right insets).
 */
function plotFraction(
  clientX: number,
  target: Element,
  padLeft: number,
  padRight: number,
  vbW: number,
): number {
  const rect = target.getBoundingClientRect();
  if (rect.width === 0) return 0.5;
  const x = ((clientX - rect.left) / rect.width) * vbW;
  const plotW = vbW - padLeft - padRight;
  if (plotW <= 0) return 0.5;
  return Math.max(0, Math.min(1, (x - padLeft) / plotW));
}

/** What a view-controlled chart needs to drive zoom/pan; null ⇒ static chart. */
interface ViewControl {
  /** plot-area right inset (differs per chart). */
  padRight: number;
  /** wheel zoom, centred on cursor clientX, against the chart's own width. */
  onWheel: (clientX: number, deltaY: number, target: Element) => void;
  onMouseDown: (e: React.MouseEvent<SVGSVGElement>) => void;
  onDoubleClick: () => void;
}

/**
 * Build the shared wheel / drag / double-click control for a ViewWindow. Returns
 * null (static chart) when not view-controlled, so the same component renders
 * statically wherever `view`/`onView` are omitted.
 */
function viewHandlers(
  view: ViewWindow | undefined,
  onView: ((v: ViewWindow) => void) | undefined,
  pad: Pick<ChartPad, "left" | "right">,
  vbW: number,
  resetTo?: ViewWindow,
): ViewControl | null {
  if (!view || !onView) return null;
  const { lo, hi } = view;
  const resetView = resetTo ?? { lo: 0, hi: 1 };

  const onWheel = (clientX: number, deltaY: number, target: Element) => {
    const span = hi - lo;
    const cursor = lo + plotFraction(clientX, target, pad.left, pad.right, vbW) * span;
    // Wheel up (deltaY < 0) zooms in; down zooms out. Centred on the cursor.
    const factor = Math.exp(deltaY * 0.0011);
    const nlo = cursor - (cursor - lo) * factor;
    const nhi = cursor + (hi - cursor) * factor;
    onView(clampView(nlo, nhi));
  };

  const onMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    e.preventDefault();
    const startX = e.clientX;
    const span = hi - lo;
    const rect = e.currentTarget.getBoundingClientRect();
    const plotPxW = rect.width * ((vbW - pad.left - pad.right) / vbW);
    const move = (me: MouseEvent) => {
      if (plotPxW === 0) return;
      // Drag right ⇒ window shifts left (content follows the cursor). Clamp the
      // shift so the window TRANSLATES (keeps its width) against the [0,1] edges
      // instead of narrowing — true pan, not zoom, at the boundary.
      let dFrac = ((me.clientX - startX) / plotPxW) * span;
      dFrac = Math.max(hi - 1, Math.min(lo, dFrac));
      onView(clampView(lo - dFrac, hi - dFrac));
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  const onDoubleClick = () => onView(resetView);

  return { padRight: pad.right, onWheel, onMouseDown, onDoubleClick };
}

function makeScale(kind: ChartScale) {
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

/** Log-scale ticks with ~targetCount labels between min and max (not just decades). */
function logTicks(realLo: number, realHi: number, targetCount = 6): number[] {
  const lo = Math.max(realLo, 1e-12);
  const hi = Math.max(realHi, lo * 1.001);
  const loLog = Math.log10(lo);
  const hiLog = Math.log10(hi);
  const span = hiLog - loLog;
  if (!Number.isFinite(span) || span <= 0) return [lo, hi];

  const roughStep = span / Math.max(2, targetCount - 1);
  const niceSteps = [0.1, 0.2, 0.3, 0.5, 1.0, 2.0];
  let logStep = niceSteps[niceSteps.length - 1]!;
  for (const s of niceSteps) {
    if (s >= roughStep - 1e-9) {
      logStep = s;
      break;
    }
  }

  const ticks: number[] = [];
  const start = Math.floor(loLog / logStep) * logStep;
  for (let lk = start; lk <= hiLog + logStep * 0.001; lk += logStep) {
    const v = Math.pow(10, lk);
    if (v + 1e-9 >= lo && v - 1e-9 <= hi) ticks.push(v);
  }
  return ticks.length >= 2 ? ticks : [lo, hi];
}

// Decade ticks for symlog, in real (untransformed) space.
function decadeTicks(kind: ChartScale, realLo: number, realHi: number): number[] {
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

function normalizeWheelDelta(e: WheelEvent): number {
  let dy = e.deltaY;
  if (e.deltaMode === WheelEvent.DOM_DELTA_LINE) dy *= 16;
  else if (e.deltaMode === WheelEvent.DOM_DELTA_PAGE) dy *= window.innerHeight;
  return dy;
}

function Svg({
  height,
  vbW = W,
  children,
  control,
  onMouseMove,
  onMouseLeave,
  preserveAspectRatio = "none",
}: {
  height: number;
  vbW?: number;
  children: ReactNode;
  control?: ViewControl | null;
  onMouseMove?: (e: React.MouseEvent<SVGSVGElement>) => void;
  onMouseLeave?: (e: React.MouseEvent<SVGSVGElement>) => void;
  preserveAspectRatio?: string;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const controlRef = useRef(control);
  const wheelAccumRef = useRef<{ clientX: number; deltaY: number } | null>(null);
  const wheelRafRef = useRef<number | null>(null);

  useEffect(() => {
    controlRef.current = control;
  }, [control]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const flushWheel = () => {
      wheelRafRef.current = null;
      const c = controlRef.current;
      const accum = wheelAccumRef.current;
      wheelAccumRef.current = null;
      if (!c || !accum) return;
      c.onWheel(accum.clientX, accum.deltaY, el);
    };

    const handler = (e: WheelEvent) => {
      if (!controlRef.current) return;
      e.preventDefault();

      const dy = normalizeWheelDelta(e);
      if (Math.abs(e.deltaX) > Math.abs(dy) * 1.25) return;

      if (wheelAccumRef.current) {
        wheelAccumRef.current.deltaY += dy;
        wheelAccumRef.current.clientX = e.clientX;
      } else {
        wheelAccumRef.current = { clientX: e.clientX, deltaY: dy };
      }
      if (wheelRafRef.current === null) {
        wheelRafRef.current = requestAnimationFrame(flushWheel);
      }
    };

    el.addEventListener("wheel", handler, { passive: false });
    return () => {
      el.removeEventListener("wheel", handler);
      if (wheelRafRef.current !== null) cancelAnimationFrame(wheelRafRef.current);
    };
  }, []);

  return (
    <svg
      ref={ref}
      viewBox={`0 0 ${vbW} ${height}`}
      preserveAspectRatio={preserveAspectRatio}
      className={"ts-svg" + (control ? " is-interactive" : "")}
      role="img"
      onMouseDown={control ? control.onMouseDown : undefined}
      onDoubleClick={control ? control.onDoubleClick : undefined}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
    >
      {children}
    </svg>
  );
}

function Empty({ height, msg, vbW = W }: { height: number; msg: string; vbW?: number }) {
  return (
    <Svg height={height} vbW={vbW}>
      <text x={vbW / 2} y={height / 2} textAnchor="middle" className="ts-svg-empty">
        {msg}
      </text>
    </Svg>
  );
}

export interface TimeSeriesProps {
  points: TearsheetSeriesPoint[];
  height?: number;
  scale?: ChartScale;
  tone?: ChartTone;
  fmt?: (v: number) => string;
  zeroBaseline?: boolean;
  /** Shared normalized x-window (date span fraction). Omit ⇒ full range, static. */
  view?: ViewWindow;
  /** Notified on wheel-zoom / drag-pan / double-click reset. */
  onView?: (v: ViewWindow) => void;
  /** Full date span [firstISO, lastISO] for the *whole* series; defaults to the
   *  series' own endpoints. Pass the shared span so every chart maps the same
   *  fraction to the same calendar window even if point counts differ. */
  fullSpan?: [string, string];
  /** Double-click / internal reset target (defaults to full range). */
  resetView?: ViewWindow;
  /** When false, omit hover tooltips (static print-first panes). */
  interactive?: boolean;
}

/**
 * Slice points to a normalized fraction window over a shared date span. The
 * fraction is mapped to a calendar window [t(lo), t(hi)] (linear in time across
 * the span), then points whose date falls inside are kept — so two series that
 * share a span stay locked to the same calendar window regardless of sampling.
 */
function sliceByView(
  points: TearsheetSeriesPoint[],
  view: ViewWindow | undefined,
  fullSpan: [string, string] | undefined,
): TearsheetSeriesPoint[] {
  if (!view || (view.lo <= 0 && view.hi >= 1) || points.length === 0) return points;
  const t0 = new Date((fullSpan ? fullSpan[0] : points[0].t)).getTime();
  const t1 = new Date((fullSpan ? fullSpan[1] : points[points.length - 1].t)).getTime();
  const span = t1 - t0;
  if (span <= 0) return points;
  const loT = t0 + view.lo * span;
  const hiT = t0 + view.hi * span;
  const out = points.filter((p) => {
    const t = new Date(p.t).getTime();
    return t >= loT && t <= hiT;
  });
  // Guarantee at least a couple of points so the path/area still draws.
  if (out.length >= 2) return out;
  const mid = (loT + hiT) / 2;
  let nearest = 0;
  for (let i = 1; i < points.length; i++) {
    if (Math.abs(new Date(points[i].t).getTime() - mid) < Math.abs(new Date(points[nearest].t).getTime() - mid)) nearest = i;
  }
  return points.slice(Math.max(0, nearest - 1), Math.min(points.length, nearest + 1));
}

/** Slice OHLC bars to the same calendar window as ``sliceByView``. */
function sliceBarsByView(
  bars: TearsheetOhlcBar[],
  view: ViewWindow | undefined,
  fullSpan: [string, string] | undefined,
): TearsheetOhlcBar[] {
  if (!view || (view.lo <= 0 && view.hi >= 1) || bars.length === 0) return bars;
  const t0 = new Date((fullSpan ? fullSpan[0] : bars[0].t)).getTime();
  const t1 = new Date((fullSpan ? fullSpan[1] : bars[bars.length - 1].t)).getTime();
  const span = t1 - t0;
  if (span <= 0) return bars;
  const loT = t0 + view.lo * span;
  const hiT = t0 + view.hi * span;
  const out = bars.filter((b) => {
    const t = new Date(b.t).getTime();
    return t >= loT && t <= hiT;
  });
  if (out.length >= 2) return out;
  const mid = (loT + hiT) / 2;
  let nearest = 0;
  for (let i = 1; i < bars.length; i++) {
    if (Math.abs(new Date(bars[i].t).getTime() - mid) < Math.abs(new Date(bars[nearest].t).getTime() - mid)) {
      nearest = i;
    }
  }
  return bars.slice(Math.max(0, nearest - 1), Math.min(bars.length, nearest + 1));
}

function barIndexForDate(bars: TearsheetOhlcBar[], iso: string): number {
  if (!iso) return -1;
  const exact = bars.findIndex((b) => b.t === iso);
  if (exact >= 0) return exact;
  const target = new Date(iso).getTime();
  if (Number.isNaN(target)) return -1;
  let best = 0;
  let bestD = Infinity;
  for (let i = 0; i < bars.length; i++) {
    const d = Math.abs(new Date(bars[i].t).getTime() - target);
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

export interface CandlestickChartProps {
  bars: TearsheetOhlcBar[];
  trades: TearsheetTrade[];
  height?: number;
  scale?: ChartScale;
  view?: ViewWindow;
  onView?: (v: ViewWindow) => void;
  fullSpan?: [string, string];
  resetView?: ViewWindow;
  /** When false, omit hover tooltips (e.g. homepage preview cards). */
  interactive?: boolean;
  /** Tighter plot padding for compact preview cards. */
  compact?: boolean;
}

/**
 * Candlestick price chart with TradingView-style entry/exit markers.
 * Long entry = buy arrow below; short entry = sell arrow above; exits flip.
 */
export function CandlestickChart(props: CandlestickChartProps) {
  const { bars: allBars, height = 380 } = props;
  if (!allBars || allBars.length === 0) return <Empty height={height} msg="no price data" />;
  return <CandlestickChartBody {...props} bars={allBars} height={height} />;
}

function CandlestickChartBody({
  bars: allBars,
  trades,
  height,
  scale: scaleKind = "linear",
  view,
  onView,
  fullSpan,
  resetView,
  interactive = true,
  compact = false,
}: CandlestickChartProps & { bars: TearsheetOhlcBar[]; height: number }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<ChartHoverTip | null>(null);
  const { vbW, pad } = useChartLayout(wrapRef, height, compact);
  const bars = sliceBarsByView(allBars, view, fullSpan);
  const control = viewHandlers(view, onView, pad, vbW, resetView);
  const scale = makeScale(scaleKind);
  const plotW = vbW - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const plotTop = pad.top;
  const plotBottom = pad.top + plotH;

  const t0 = new Date((fullSpan ? fullSpan[0] : bars[0].t)).getTime();
  const t1 = new Date((fullSpan ? fullSpan[1] : bars[bars.length - 1].t)).getTime();
  const winLo = view && !(view.lo <= 0 && view.hi >= 1) && t1 > t0 ? t0 + view.lo * (t1 - t0) : t0;
  const winHi = view && !(view.lo <= 0 && view.hi >= 1) && t1 > t0 ? t0 + view.hi * (t1 - t0) : t1;

  const inWin = (iso: string) => {
    if (!iso) return false;
    const t = new Date(iso).getTime();
    return t >= winLo && t <= winHi;
  };

  const priceVals: number[] = [];
  for (const b of bars) {
    priceVals.push(b.l, b.h);
  }
  for (const t of trades) {
    if (!inWin(t.entry_date) && !( !isOpenTrade(t) && inWin(t.exit_date))) continue;
    if (t.entry_price > 0) priceVals.push(t.entry_price);
    if (!isOpenTrade(t) && t.exit_price > 0) priceVals.push(t.exit_price);
  }

  const { lo: loF, hi: hiF } = dataDomain(priceVals, scale, { padRatio: 0.04 });

  const n = bars.length;

  const slotEst = n > 1 ? plotW / (n - 1) : plotW;
  const bodyEst = Math.max(1.2, Math.min(slotEst * 0.65, 10));
  // Inset candles from the right edge so the latest bar (and markers) are not clipped.
  const rightGutter = compact
    ? Math.max(bodyEst * 0.45, plotW * 0.015)
    : Math.max(bodyEst * 0.85, plotW * 0.06);
  const leftGutter = compact ? bodyEst * 0.2 : bodyEst * 0.45;
  const xSpan = Math.max(plotW * 0.2, plotW - leftGutter - rightGutter);
  const xAt = (i: number) =>
    pad.left + leftGutter + (n === 1 ? xSpan / 2 : (i / (n - 1)) * xSpan);
  const yAt = (val: number) => plotBottom - ((scale.f(val) - loF) / (hiF - loF)) * plotH;

  const realLo = scale.inv(loF);
  const realHi = scale.inv(hiF);
  const ticks =
    scaleKind === "log"
      ? logTicks(realLo, realHi, 6)
      : niceLinearTicks(realLo, realHi, 5);

  const gridEls: ReactNode[] = [];
  ticks.forEach((tv, i) => {
    const y = yAt(tv);
    if (y < plotTop - 1 || y > plotBottom + 1) return;
    gridEls.push(
      <line key={`g${i}`} x1={pad.left} y1={y} x2={vbW - pad.right} y2={y} className="ts-grid" />,
      <text key={`gt${i}`} x={pad.left - 6} y={axisLabelY(y, plotTop, plotBottom)} textAnchor="end" className="ts-axis">
        {fmtCompact(tv)}
      </text>,
    );
  });

  const slot = n > 1 ? xSpan / (n - 1) : xSpan;
  const bodyW = Math.max(1.2, Math.min(slot * 0.65, 10));

  const candleEls: ReactNode[] = bars.map((b, i) => {
    const x = xAt(i);
    const bull = b.c >= b.o;
    const yO = yAt(b.o);
    const yC = yAt(b.c);
    const yH = yAt(b.h);
    const yL = yAt(b.l);
    const top = Math.min(yO, yC);
    const h = Math.max(1, Math.abs(yC - yO));
    const tone = bull ? "up" : "down";
    return (
      <g key={`c${i}`} className={"ts-candle ts-candle-" + tone}>
        <line x1={x} y1={yH} x2={x} y2={yL} className="ts-candle-wick" />
        <rect x={x - bodyW / 2} y={top} width={bodyW} height={h} className="ts-candle-body" rx={0.4} />
      </g>
    );
  });

  const markerEls: ReactNode[] = [];
  const markerHits: MarkerHit[] = [];

  const addMarker = (
    x: number,
    y: number,
    kind: "buy" | "sell",
    role: "entry" | "exit",
    key: string,
    trade: TearsheetTrade,
  ) => {
    const scaleM = Math.max(1, Math.min(2.5, slot / 5.5));
    const hw = 7.5 * scaleM;
    const th = 12 * scaleM;
    const gap = Math.max(11, 9 + th * 0.3);
    const d =
      kind === "buy"
        ? `M${x} ${y + gap} L${x - hw} ${y + gap + th} L${x + hw} ${y + gap + th} Z`
        : `M${x} ${y - gap} L${x - hw} ${y - gap - th} L${x + hw} ${y - gap - th} Z`;
    const hitY = kind === "buy" ? y + gap + th * 0.55 : y - gap - th * 0.55;
    markerHits.push({ x, y: hitY, role, trade });
    markerEls.push(
      <g key={key} className={"ts-marker-wrap ts-marker-wrap-" + kind} aria-hidden="true">
        <path d={d} className="ts-marker-halo" />
        <path d={d} className={"ts-marker ts-marker-" + kind} />
      </g>,
    );
  };

  for (const t of trades) {
    if (inWin(t.entry_date)) {
      const i = barIndexForDate(bars, t.entry_date);
      if (i >= 0) {
        const x = xAt(i);
        const y = yAt(t.entry_price);
        addMarker(x, y, t.direction === "long" ? "buy" : "sell", "entry", `e${t.n}`, t);
      }
    }
    if (!isOpenTrade(t) && inWin(t.exit_date)) {
      const i = barIndexForDate(bars, t.exit_date);
      if (i >= 0) {
        const x = xAt(i);
        const y = yAt(t.exit_price);
        addMarker(x, y, t.direction === "long" ? "sell" : "buy", "exit", `x${t.n}`, t);
      }
    }
  }

  const idxs = [0, Math.floor((n - 1) / 2), n - 1];

  const onChartMouseMove = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (e.buttons !== 0) {
        setHover(null);
        return;
      }
      const wrap = wrapRef.current;
      if (!wrap) return;
      const { x: vbX, y: vbY } = viewBoxPoint(e.clientX, e.clientY, e.currentTarget, vbW, height);
      if (vbX < pad.left || vbX > vbW - pad.right || vbY < plotTop || vbY > plotBottom) {
        setHover(null);
        return;
      }
      const marker = hitMarker(vbX, vbY, markerHits);
      const pos = positionHoverTip(e.clientX, e.clientY, wrap, 220, marker ? 108 : 132);
      if (marker) {
        setHover({ ...pos, content: <TradeTipContent trade={marker.trade} /> });
        return;
      }
      const bi = nearestBarIndex(vbX, n, xAt, slot * 0.55);
      if (bi < 0) {
        setHover(null);
        return;
      }
      setHover({ ...pos, content: <OhlcTipContent bar={bars[bi]} /> });
    },
    [bars, height, markerHits, n, pad.left, pad.right, plotBottom, plotTop, slot, vbW, xAt],
  );

  const onChartMouseLeave = useCallback(() => setHover(null), []);

  return (
    <ChartHoverShell hover={interactive ? hover : null} wrapRef={wrapRef}>
      <Svg
        height={height}
        vbW={vbW}
        control={control}
        onMouseMove={interactive ? onChartMouseMove : undefined}
        onMouseLeave={interactive ? onChartMouseLeave : undefined}
      >
      <defs>
        <clipPath id="ts-candle-clip">
          <rect x={pad.left} y={plotTop} width={plotW} height={plotH} />
        </clipPath>
      </defs>
      {gridEls}
      <g clipPath="url(#ts-candle-clip)">{candleEls}</g>
      <g className="ts-marker-layer">{markerEls}</g>
      {idxs.map((i, k) => {
        const anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
        const xAxisY = compact ? height - 6 : height - 10;
        return (
          <text key={`x${k}`} x={xAt(i)} y={xAxisY} textAnchor={anchor} className="ts-axis">
            {(bars[i].t || "").slice(0, 10)}
          </text>
        );
      })}
        </Svg>
    </ChartHoverShell>
  );
}

/** Time-series area/line chart. */
export function TimeSeries(props: TimeSeriesProps) {
  const { points: allPoints, height = 320 } = props;
  if (!allPoints || allPoints.length === 0) return <Empty height={height} msg="no data" />;
  return <TimeSeriesBody {...props} points={allPoints} height={height} />;
}

function TimeSeriesBody({
  points: allPoints,
  height,
  scale: scaleKind = "linear",
  tone = "accent",
  fmt = fmtCompact,
  zeroBaseline = false,
  view,
  onView,
  fullSpan,
  resetView,
  interactive = true,
}: TimeSeriesProps & { points: TearsheetSeriesPoint[]; height: number }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<ChartHoverTip | null>(null);
  const { vbW, pad } = useChartLayout(wrapRef, height, false);
  const points = sliceByView(allPoints, view, fullSpan);
  const control = viewHandlers(view, onView, pad, vbW, resetView);
  const scale = makeScale(scaleKind);
  const plotW = vbW - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const plotTop = pad.top;
  const plotBottom = pad.top + plotH;

  const values = points.map((p) => p.v);
  const { lo, hi } = dataDomain(values, scale, {
    padRatio: 0.05,
    anchorZero: zeroBaseline ? "max" : undefined,
  });

  const n = points.length;
  const xAt = (i: number) => pad.left + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const yAt = (val: number) => pad.top + plotH - ((scale.f(val) - lo) / (hi - lo)) * plotH;

  const realLo = scale.inv(lo), realHi = scale.inv(hi);
  const ticks =
    scaleKind === "log"
      ? logTicks(realLo, realHi, 6)
      : scaleKind === "symlog"
        ? decadeTicks("symlog", realLo, realHi)
        : niceLinearTicks(realLo, realHi, 4);

  const gridEls: ReactNode[] = [];
  ticks.forEach((tv, i) => {
    const y = yAt(tv);
    if (y < plotTop - 1 || y > plotBottom + 1) return;
    gridEls.push(
      <line key={`g${i}`} x1={pad.left} y1={y} x2={vbW - pad.right} y2={y} className={"ts-grid" + (tv === 0 ? " ts-grid-zero" : "")} />,
      <text key={`gt${i}`} x={pad.left - 8} y={axisLabelY(y, plotTop, plotBottom)} textAnchor="end" className="ts-axis">{fmt(tv)}</text>,
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

  const onChartMouseMove = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (e.buttons !== 0) {
        setHover(null);
        return;
      }
      const wrap = wrapRef.current;
      if (!wrap) return;
      const { x: vbX, y: vbY } = viewBoxPoint(e.clientX, e.clientY, e.currentTarget, vbW, height);
      if (vbX < pad.left || vbX > vbW - pad.right || vbY < plotTop || vbY > plotBottom) {
        setHover(null);
        return;
      }
      const frac = plotFraction(e.clientX, e.currentTarget, pad.left, pad.right, vbW);
      const idx = n === 1 ? 0 : Math.round(frac * (n - 1));
      const pt = points[idx];
      if (!pt) {
        setHover(null);
        return;
      }
      const pos = positionHoverTip(e.clientX, e.clientY, wrap, 180, 72);
      setHover({
        ...pos,
        content: <SeriesTipContent date={pt.t} value={fmt(pt.v)} />,
      });
    },
    [fmt, height, n, pad.left, pad.right, plotBottom, plotTop, points, vbW],
  );

  const onChartMouseLeave = useCallback(() => setHover(null), []);

  return (
    <ChartHoverShell hover={interactive ? hover : null} wrapRef={wrapRef}>
      <Svg
        height={height}
        vbW={vbW}
        control={control}
        onMouseMove={interactive ? onChartMouseMove : undefined}
        onMouseLeave={interactive ? onChartMouseLeave : undefined}
      >
      <defs>
        <clipPath id="ts-series-clip">
          <rect x={pad.left} y={plotTop} width={plotW} height={plotH} />
        </clipPath>
      </defs>
      {gridEls}
      <g clipPath="url(#ts-series-clip)">
        <path d={area} className={"ts-area ts-tone-" + tone} />
        <path d={line} className={"ts-line ts-tone-" + tone} fill="none" />
      </g>
      {idxs.map((i, k) => {
        const anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
        return (
          <text key={`x${k}`} x={xAt(i)} y={height - 10} textAnchor={anchor} className="ts-axis">
            {(points[i].t || "").slice(0, 10)}
          </text>
        );
      })}
      </Svg>
    </ChartHoverShell>
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
      <text key={`gt${i}`} x={PAD.left - 10} y={y + 4} textAnchor="end" className="ts-axis">{fmt(tv)}</text>,
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

export interface ContributionReturnPoint {
  t: string;
  /** Exact cumulative portfolio return from the NAV series, in percent. */
  returnPct: number;
  /** Cumulative per-position contribution, in percentage points. */
  contributions: Record<string, number>;
}

export interface ContributionReturnChartProps {
  points: ContributionReturnPoint[];
  /** Stable series identity colors supplied by the consuming product. */
  colors: Record<string, string>;
  height?: number;
  interactive?: boolean;
}

/** Signed cumulative contribution stacks with the exact portfolio return overlaid. */
export function ContributionReturnChart({
  points,
  colors,
  height = 360,
  interactive = true,
}: ContributionReturnChartProps) {
  if (points.length < 2) return <Empty height={height} msg="not enough history" />;
  return (
    <ContributionReturnChartBody
      points={points}
      colors={colors}
      height={height}
      interactive={interactive}
    />
  );
}

function ContributionReturnChartBody({
  points,
  colors,
  height,
  interactive,
}: Required<ContributionReturnChartProps>) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<ChartHoverTip | null>(null);
  const { vbW, pad } = useChartLayout(wrapRef, height, false);
  const plotW = vbW - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const plotBottom = pad.top + plotH;
  const keys = [...new Set(points.flatMap((point) => Object.keys(point.contributions)))];
  const extents = points.map((point) => {
    let positive = 0;
    let negative = 0;
    for (const value of Object.values(point.contributions)) {
      if (value >= 0) positive += value;
      else negative += value;
    }
    return { positive, negative };
  });
  const values = [
    ...points.map((point) => point.returnPct),
    ...extents.flatMap((extent) => [extent.positive, extent.negative]),
    0,
  ];
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (lo === hi) hi = lo + 1;
  const domainPad = (hi - lo) * 0.08;
  lo -= domainPad;
  hi += domainPad;
  const yAt = (value: number) => pad.top + plotH - ((value - lo) / (hi - lo)) * plotH;
  const zeroY = yAt(0);
  const slot = plotW / points.length;
  const barWidth = Math.max(1, Math.min(slot * 0.72, 24));
  const xCenter = (index: number) => pad.left + slot * index + slot / 2;
  const line = points
    .map((point, index) => `${index ? 'L' : 'M'}${xCenter(index).toFixed(1)} ${yAt(point.returnPct).toFixed(1)}`)
    .join(' ');

  const grid: ReactNode[] = [];
  niceLinearTicks(lo, hi, 4).forEach((tick, index) => {
    const y = yAt(tick);
    grid.push(
      <line key={`g${index}`} x1={pad.left} y1={y} x2={vbW - pad.right} y2={y} className={`ts-grid${tick === 0 ? ' ts-grid-zero' : ''}`} />,
      <text key={`gt${index}`} x={pad.left - 8} y={axisLabelY(y, pad.top, plotBottom)} textAnchor="end" className="ts-axis">{fmtCompact(tick)}%</text>,
    );
  });

  const onChartMouseMove = useCallback((event: React.MouseEvent<SVGSVGElement>) => {
    if (event.buttons !== 0) {
      setHover(null);
      return;
    }
    const wrap = wrapRef.current;
    if (!wrap) return;
    const { x, y } = viewBoxPoint(event.clientX, event.clientY, event.currentTarget, vbW, height);
    if (x < pad.left || x > vbW - pad.right || y < pad.top || y > plotBottom) {
      setHover(null);
      return;
    }
    const index = Math.max(0, Math.min(points.length - 1, Math.floor((x - pad.left) / slot)));
    setHover({
      ...positionHoverTip(event.clientX, event.clientY, wrap, 220, 128),
      content: <ContributionReturnTipContent point={points[index]} colors={colors} />,
    });
  }, [height, pad.left, pad.right, pad.top, plotBottom, points, slot, vbW]);

  return (
    <ChartHoverShell hover={interactive ? hover : null} wrapRef={wrapRef}>
      <Svg
        height={height}
        vbW={vbW}
        onMouseMove={interactive ? onChartMouseMove : undefined}
        onMouseLeave={interactive ? () => setHover(null) : undefined}
      >
        <defs>
          <clipPath id="ts-contribution-return-clip">
            <rect x={pad.left} y={pad.top} width={plotW} height={plotH} />
          </clipPath>
        </defs>
        {grid}
        <g clipPath="url(#ts-contribution-return-clip)" data-chart-layer="contributions">
          {points.flatMap((point, index) => {
            let positive = 0;
            let negative = 0;
            return keys.flatMap((key) => {
              const value = point.contributions[key] ?? 0;
              if (value === 0) return [];
              const start = value >= 0 ? positive : negative;
              const end = start + value;
              if (value >= 0) positive = end;
              else negative = end;
              const top = Math.min(yAt(start), yAt(end));
              return (
                <rect
                  key={`${point.t}:${key}`}
                  x={(xCenter(index) - barWidth / 2).toFixed(1)}
                  y={top.toFixed(1)}
                  width={barWidth.toFixed(1)}
                  height={Math.max(0.75, Math.abs(yAt(end) - yAt(start))).toFixed(1)}
                  fill={colors[key] ?? 'var(--ink-mute)'}
                  className="ts-contribution-segment"
                  data-series={key}
                />
              );
            });
          })}
          <line x1={pad.left} y1={zeroY} x2={vbW - pad.right} y2={zeroY} className="ts-grid ts-grid-zero" />
          <path d={line} className="ts-line ts-tone-accent ts-portfolio-return-line" fill="none" data-chart-layer="portfolio-return" />
          {points.map((point, index) => (
            <circle key={point.t} cx={xCenter(index)} cy={yAt(point.returnPct)} r="2.5" className="ts-portfolio-return-dot" />
          ))}
        </g>
        {[0, Math.floor((points.length - 1) / 2), points.length - 1].map((index) => (
          <text
            key={`${points[index].t}:${index}`}
            x={xCenter(index)}
            y={height - 10}
            textAnchor={index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle'}
            className="ts-axis"
          >
            {points[index].t.slice(0, 10)}
          </text>
        ))}
      </Svg>
    </ChartHoverShell>
  );
}

/** Per-trade realized/unrealized return % (single-axis bar chart). */
export interface TradeReturnChartProps {
  bars: TradeReturnBar[];
  height?: number;
  view?: ViewWindow;
  onView?: (v: ViewWindow) => void;
  fullSpan?: [string, string];
  resetView?: ViewWindow;
  /** When false, omit hover tooltips (static print-first panes). */
  interactive?: boolean;
}

function sliceTradeBarsByView(
  bars: TradeReturnBar[],
  view: ViewWindow | undefined,
  fullSpan: [string, string] | undefined,
): TradeReturnBar[] {
  if (!view || (view.lo <= 0 && view.hi >= 1) || bars.length === 0) return bars;
  const t0 = new Date((fullSpan ? fullSpan[0] : bars[0].t)).getTime();
  const t1 = new Date((fullSpan ? fullSpan[1] : bars[bars.length - 1].t)).getTime();
  const span = t1 - t0;
  if (span <= 0) return bars;
  const loT = t0 + view.lo * span;
  const hiT = t0 + view.hi * span;
  const out = bars.filter((b) => {
    const t = new Date(b.t).getTime();
    return t >= loT && t <= hiT;
  });
  if (out.length > 0) return out;
  const mid = (loT + hiT) / 2;
  let nearest = 0;
  for (let i = 1; i < bars.length; i++) {
    if (Math.abs(new Date(bars[i].t).getTime() - mid) < Math.abs(new Date(bars[nearest].t).getTime() - mid)) {
      nearest = i;
    }
  }
  return bars.slice(Math.max(0, nearest - 1), Math.min(bars.length, nearest + 1));
}

/**
 * Per-trade return % bars in trade order. Open leg is appended last and styled
 * as unrealized. Shares zoom/pan with the other time-series charts.
 */
export function TradeReturnChart(props: TradeReturnChartProps) {
  const { bars: allBars, height = 300 } = props;
  if (!allBars || allBars.length === 0) return <Empty height={height} msg="no trades" />;
  const bars = sliceTradeBarsByView(allBars, props.view, props.fullSpan);
  if (bars.length === 0) return <Empty height={height} msg="no trades in window" />;
  return <TradeReturnChartBody {...props} bars={bars} height={height} />;
}

function TradeReturnChartBody({
  bars,
  height,
  view,
  onView,
  resetView,
  interactive = true,
}: TradeReturnChartProps & { bars: TradeReturnBar[]; height: number }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<ChartHoverTip | null>(null);
  const { vbW, pad } = useChartLayout(wrapRef, height, false);
  const control = viewHandlers(view, onView, pad, vbW, resetView);

  const plotW = vbW - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const plotTop = pad.top;
  const plotBottom = pad.top + plotH;
  const n = bars.length;
  const slot = plotW / n;
  const bw = Math.max(0.6, Math.min(slot * 0.7, 16));
  const xCenter = (i: number) => pad.left + (i + 0.5) * slot;

  let lo = 0;
  let hi = 0;
  for (const b of bars) {
    if (b.pct < lo) lo = b.pct;
    if (b.pct > hi) hi = b.pct;
  }
  if (lo === hi) hi = lo + (lo >= 0 ? 1 : -1);
  const padF = (hi - lo) * 0.08;
  lo -= padF;
  hi += padF;

  const yAt = (v: number) => pad.top + plotH - ((v - lo) / (hi - lo)) * plotH;
  const zeroY = yAt(0);
  const fmtPctAxis = (v: number) => fmtCompact(v) + "%";

  const gridEls: ReactNode[] = [];
  niceLinearTicks(lo, hi, 4).forEach((tv, i) => {
    const y = yAt(tv);
    if (y < plotTop - 1 || y > plotBottom + 1) return;
    gridEls.push(
      <line key={`g${i}`} x1={pad.left} y1={y} x2={vbW - pad.right} y2={y} className={"ts-grid" + (tv === 0 ? " ts-grid-zero" : "")} />,
      <text key={`gt${i}`} x={pad.left - 8} y={axisLabelY(y, plotTop, plotBottom)} textAnchor="end" className="ts-axis">
        {fmtPctAxis(tv)}
      </text>,
    );
  });

  const idxs = [0, Math.floor((n - 1) / 2), n - 1];

  const onChartMouseMove = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (e.buttons !== 0) {
        setHover(null);
        return;
      }
      const wrap = wrapRef.current;
      if (!wrap) return;
      const { x: vbX, y: vbY } = viewBoxPoint(e.clientX, e.clientY, e.currentTarget, vbW, height);
      if (vbX < pad.left || vbX > vbW - pad.right || vbY < plotTop || vbY > plotBottom) {
        setHover(null);
        return;
      }
      const relX = vbX - pad.left;
      const idx = Math.min(n - 1, Math.max(0, Math.floor(relX / slot)));
      const bar = bars[idx];
      if (!bar?.trade) {
        setHover(null);
        return;
      }
      const pos = positionHoverTip(e.clientX, e.clientY, wrap, 220, 120);
      setHover({
        ...pos,
        content: <TradeTipContent trade={bar.trade} showPnlMoney />,
      });
    },
    [bars, height, n, pad.left, pad.right, plotBottom, plotTop, slot, vbW],
  );

  const onChartMouseLeave = useCallback(() => setHover(null), []);

  return (
    <ChartHoverShell hover={interactive ? hover : null} wrapRef={wrapRef}>
      <Svg
        height={height}
        vbW={vbW}
        control={control}
        onMouseMove={interactive ? onChartMouseMove : undefined}
        onMouseLeave={interactive ? onChartMouseLeave : undefined}
      >
      <defs>
        <clipPath id="ts-pnl-clip">
          <rect x={pad.left} y={plotTop} width={plotW} height={plotH} />
        </clipPath>
      </defs>
      {gridEls}
      <g clipPath="url(#ts-pnl-clip)">
        {bars.map((b, i) => {
          const x = pad.left + i * slot + (slot - bw) / 2;
          const y = b.pct >= 0 ? yAt(b.pct) : zeroY;
          const h = Math.max(0.5, Math.abs(yAt(b.pct) - zeroY));
          const tone = b.pct >= 0 ? "up" : "down";
          return (
            <rect
              key={`${b.t}-${i}`}
              x={x.toFixed(1)}
              y={y.toFixed(1)}
              width={bw.toFixed(1)}
              height={h.toFixed(1)}
              className={"ts-bar ts-tone-" + tone + (b.open ? " ts-bar-open" : "")}
            />
          );
        })}
      </g>
      {idxs.map((i, k) => {
        const anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
        const label = bars[i].open ? "open" : (bars[i].t || "").slice(0, 10);
        return (
          <text key={`x${k}`} x={xCenter(i)} y={height - 10} textAnchor={anchor} className="ts-axis">
            {label}
          </text>
        );
      })}
      </Svg>
    </ChartHoverShell>
  );
}

