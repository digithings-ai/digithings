/**
 * Dependency-free SVG charts for strategy tearsheets (React port of the
 * standalone renderer). Pure vector output (no canvas, no libs) so the tearsheet
 * prints to PDF crisply. Charts render into a 0 0 1000 H viewBox and scale to the
 * container width. Colours come from CSS custom properties on the chart classes
 * (theme-aware via [data-theme]). Supports linear / log / symlog y scales —
 * symlog handles series that cross zero (cumulative P&L).
 *
 * Engine ruling (#1450 F2): these surfaces stay SVG — the PDF export re-renders
 * the same components, so the promoted lightweight-charts finance family
 * (canvas) is not adopted here. See ./CHARTS.md before swapping engines.
 */
import { type ReactNode, type RefObject, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { fmtCompact, fmtMoney, fmtNum, fmtPct, toneClass } from "./format";
import { annualizedVolPct, dailyReturnsFromEquity } from "./stats";
import { isOpenTrade, type TradeReturnBar } from "./trades";
import { type OHLCBar, type TearsheetPoint, type TearsheetTrade } from "./types";

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

function OhlcTipContent({ bar }: { bar: OHLCBar }) {
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

export type Scale = "linear" | "log" | "symlog";
export type Tone = "accent" | "up" | "down";

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
  points: TearsheetPoint[];
  height?: number;
  scale?: Scale;
  tone?: Tone;
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
}

/**
 * Slice points to a normalized fraction window over a shared date span. The
 * fraction is mapped to a calendar window [t(lo), t(hi)] (linear in time across
 * the span), then points whose date falls inside are kept — so two series that
 * share a span stay locked to the same calendar window regardless of sampling.
 */
function sliceByView(
  points: TearsheetPoint[],
  view: ViewWindow | undefined,
  fullSpan: [string, string] | undefined,
): TearsheetPoint[] {
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
  bars: OHLCBar[],
  view: ViewWindow | undefined,
  fullSpan: [string, string] | undefined,
): OHLCBar[] {
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

function barIndexForDate(bars: OHLCBar[], iso: string): number {
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
  bars: OHLCBar[];
  trades: TearsheetTrade[];
  height?: number;
  scale?: Scale;
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
}: CandlestickChartProps & { bars: OHLCBar[]; height: number }) {
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
}: TimeSeriesProps & { points: TearsheetPoint[]; height: number }) {
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
    <ChartHoverShell hover={hover} wrapRef={wrapRef}>
      <Svg height={height} vbW={vbW} control={control} onMouseMove={onChartMouseMove} onMouseLeave={onChartMouseLeave}>
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

/** Per-trade realized/unrealized return % (single-axis bar chart). */
export interface TradeReturnChartProps {
  bars: TradeReturnBar[];
  height?: number;
  view?: ViewWindow;
  onView?: (v: ViewWindow) => void;
  fullSpan?: [string, string];
  resetView?: ViewWindow;
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
    <ChartHoverShell hover={hover} wrapRef={wrapRef}>
      <Svg height={height} vbW={vbW} control={control} onMouseMove={onChartMouseMove} onMouseLeave={onChartMouseLeave}>
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

// ----------------------------- Returns matrix ------------------------------

export type ReturnsPeriod = "monthly" | "quarterly" | "annual";
export type MatrixMetric = "return" | "drawdown" | "volatility";

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const QUARTER_LABELS = ["Q1", "Q2", "Q3", "Q4"];

/** A single rendered cell value (or null = no data in that slot). */
interface MatrixCell {
  value: number | null;
}
interface MatrixRow {
  year: number;
  cells: MatrixCell[];
  yearValue: number | null;
}

/** Number of columns per granularity (the trailing Year column is separate). */
function colCount(period: ReturnsPeriod): number {
  return period === "monthly" ? 12 : period === "quarterly" ? 4 : 1;
}

function slotOf(month: number, period: ReturnsPeriod): number {
  return period === "monthly" ? month : period === "quarterly" ? Math.floor(month / 3) : 0;
}

function bucketEquityBySlot(points: TearsheetPoint[], period: ReturnsPeriod) {
  const lastInSlot = new Map<string, number>();
  const pointsInSlot = new Map<string, TearsheetPoint[]>();
  const yearLast = new Map<number, number>();
  let minYear = Infinity;
  let maxYear = -Infinity;

  for (const p of points) {
    const d = new Date(p.t);
    const year = d.getUTCFullYear();
    const slot = slotOf(d.getUTCMonth(), period);
    const key = `${year}:${slot}`;
    lastInSlot.set(key, p.v);
    const bucket = pointsInSlot.get(key) ?? [];
    bucket.push(p);
    pointsInSlot.set(key, bucket);
    yearLast.set(year, p.v);
    if (year < minYear) minYear = year;
    if (year > maxYear) maxYear = year;
  }
  return { lastInSlot, pointsInSlot, yearLast, minYear, maxYear };
}

function bucketDrawdownBySlot(points: TearsheetPoint[], period: ReturnsPeriod) {
  const minInSlot = new Map<string, number>();
  const yearMin = new Map<number, number>();
  let minYear = Infinity;
  let maxYear = -Infinity;

  for (const p of points) {
    const d = new Date(p.t);
    const year = d.getUTCFullYear();
    const slot = slotOf(d.getUTCMonth(), period);
    const key = `${year}:${slot}`;
    const prev = minInSlot.get(key);
    minInSlot.set(key, prev === undefined ? p.v : Math.min(prev, p.v));
    const yPrev = yearMin.get(year);
    yearMin.set(year, yPrev === undefined ? p.v : Math.min(yPrev, p.v));
    if (year < minYear) minYear = year;
    if (year > maxYear) maxYear = year;
  }
  return { minInSlot, yearMin, minYear, maxYear };
}

/**
 * Period matrix from equity (returns, vol) or drawdown curve (max DD per slot).
 */
function buildMatrixRows(
  equity: TearsheetPoint[],
  drawdown: TearsheetPoint[] | undefined,
  period: ReturnsPeriod,
  metric: MatrixMetric,
): MatrixRow[] {
  if (!equity || equity.length === 0) return [];
  const cols = colCount(period);

  if (metric === "drawdown") {
    if (!drawdown || drawdown.length === 0) return [];
    const { minInSlot, yearMin, minYear, maxYear } = bucketDrawdownBySlot(drawdown, period);
    if (!Number.isFinite(minYear)) return [];
    const rows: MatrixRow[] = [];
    for (let year = minYear; year <= maxYear; year++) {
      const cells: MatrixCell[] = [];
      for (let s = 0; s < cols; s++) {
        const v = minInSlot.get(`${year}:${s}`);
        cells.push({ value: v === undefined ? null : v });
      }
      const yv = yearMin.get(year);
      rows.push({ year, cells, yearValue: yv === undefined ? null : yv });
    }
    return rows;
  }

  const { lastInSlot, pointsInSlot, yearLast, minYear, maxYear } = bucketEquityBySlot(
    equity,
    period,
  );
  if (!Number.isFinite(minYear)) return [];

  if (metric === "volatility") {
    const rows: MatrixRow[] = [];
    for (let year = minYear; year <= maxYear; year++) {
      const cells: MatrixCell[] = [];
      for (let s = 0; s < cols; s++) {
        const pts = pointsInSlot.get(`${year}:${s}`);
        const vol =
          pts && pts.length >= 2 ? annualizedVolPct(dailyReturnsFromEquity(pts)) : null;
        cells.push({ value: vol });
      }
      const yearPts = equity.filter((p) => new Date(p.t).getUTCFullYear() === year);
      const yearVol =
        yearPts.length >= 2 ? annualizedVolPct(dailyReturnsFromEquity(yearPts)) : null;
      rows.push({ year, cells, yearValue: yearVol });
    }
    return rows;
  }

  const opening = equity[0].v;
  const rows: MatrixRow[] = [];
  let prevClose = opening;

  for (let year = minYear; year <= maxYear; year++) {
    const cells: MatrixCell[] = [];
    for (let s = 0; s < cols; s++) {
      const close = lastInSlot.get(`${year}:${s}`);
      if (close === undefined) {
        cells.push({ value: null });
      } else {
        const ret = prevClose > 0 ? (close / prevClose - 1) * 100 : null;
        cells.push({ value: ret });
        prevClose = close;
      }
    }
    const last = yearLast.get(year);
    const yearValue =
      last !== undefined && prevCloseAtYearStart(year, minYear, opening, yearLast) > 0
        ? (last / prevCloseAtYearStart(year, minYear, opening, yearLast) - 1) * 100
        : null;
    rows.push({ year, cells, yearValue: yearValue });
  }
  return rows;
}

/** Equity carried into `year`: the prior year's last close, or the opening for the
 *  first year. Keeps the Year column consistent with the chained cell logic. */
function prevCloseAtYearStart(year: number, minYear: number, opening: number, yearLast: Map<number, number>): number {
  if (year === minYear) return opening;
  // Walk back to the most recent prior year that actually has data.
  for (let y = year - 1; y >= minYear; y--) {
    const v = yearLast.get(y);
    if (v !== undefined) return v;
  }
  return opening;
}

/** Inline cell background: tone-coloured with alpha scaled by |value| relative to max-abs. */
function cellBg(value: number | null, maxAbs: number, metric: MatrixMetric): string {
  if (value === null) return "transparent";
  if (value === 0 && metric === "return") return "transparent";
  const tone =
    metric === "drawdown" || metric === "volatility"
      ? "var(--down)"
      : value > 0
        ? "var(--up)"
        : "var(--down)";
  const mag = maxAbs > 0 ? Math.abs(value) / maxAbs : 0;
  const pct = Math.round(14 + Math.min(1, mag) * 58);
  return `color-mix(in srgb, ${tone} ${pct}%, transparent)`;
}

/** Compact cell % — sheds decimals as magnitude grows so wide crypto returns
 *  (hundreds / thousands of %) fit the narrow grid cells without truncation. */
function fmtCellPct(v: number | null): string {
  if (v === null) return "";
  const a = Math.abs(v);
  if (a >= 1000) return fmtCompact(v) + "%";
  if (a >= 100) return v.toFixed(0) + "%";
  return v.toFixed(1) + "%";
}

function fmtCellValue(v: number | null, metric: MatrixMetric): string {
  if (v === null) return "";
  if (metric === "volatility") return v.toFixed(1) + "%";
  return fmtCellPct(v);
}

/**
 * Calendar heatmap of period returns derived from the equity curve. Rows = years,
 * columns = months / quarters / a single annual cell, plus a trailing compounded
 * "Year" column. Pure CSS-grid table (no SVG) so it reflows and scrolls on mobile.
 */
export function ReturnsMatrix({
  points,
  drawdown,
  period,
  metric = "return",
}: {
  points: TearsheetPoint[];
  drawdown?: TearsheetPoint[];
  period: ReturnsPeriod;
  metric?: MatrixMetric;
}) {
  const rows = buildMatrixRows(points, drawdown, period, metric);
  if (rows.length === 0) {
    return (
      <div className="ts-status">
        {metric === "drawdown" && !drawdown?.length ? "drawdown data unavailable" : "no data"}
      </div>
    );
  }

  const cols = colCount(period);
  const labels = period === "monthly" ? MONTH_LABELS : period === "quarterly" ? QUARTER_LABELS : ["Year"];
  const showYearCol = period !== "annual";

  let maxAbs = 0;
  for (const r of rows) {
    for (const c of r.cells) if (c.value !== null) maxAbs = Math.max(maxAbs, Math.abs(c.value));
    if (showYearCol && r.yearValue !== null) maxAbs = Math.max(maxAbs, Math.abs(r.yearValue));
  }

  const gridTemplate = `minmax(3rem, auto) repeat(${cols + (showYearCol ? 1 : 0)}, minmax(0, 1fr))`;
  const metricLabel = metric === "return" ? "returns" : metric === "drawdown" ? "drawdown" : "volatility";

  return (
    <div className="ts-table-wrap ts-matrix-wrap">
      <div
        className="ts-matrix ts-matrix-fill"
        style={{ gridTemplateColumns: gridTemplate }}
        role="table"
        aria-label={`${period} ${metricLabel}`}
      >
        <div className="ts-matrix-corner" role="columnheader" />
        {labels.map((l) => (
          <div key={l} className="ts-matrix-head" role="columnheader">{l}</div>
        ))}
        {showYearCol ? <div className="ts-matrix-head ts-matrix-year-head" role="columnheader">Year</div> : null}
        {rows.map((r) => (
          <div key={r.year} className="ts-matrix-row" role="row" style={{ display: "contents" }}>
            <div className="ts-matrix-rowlabel" role="rowheader">{r.year}</div>
            {r.cells.map((c, i) => (
              <div
                key={i}
                className={"ts-matrix-cell" + (c.value === null ? " is-empty" : "")}
                style={{ background: cellBg(c.value, maxAbs, metric) }}
                role="cell"
                title={
                  c.value === null
                    ? "no data"
                    : `${labels[i]} ${r.year}: ${fmtCellValue(c.value, metric)}`
                }
              >
                {fmtCellValue(c.value, metric)}
              </div>
            ))}
            {showYearCol ? (
              <div
                className={"ts-matrix-cell ts-matrix-year" + (r.yearValue === null ? " is-empty" : "")}
                style={{ background: cellBg(r.yearValue, maxAbs, metric) }}
                role="cell"
                title={
                  r.yearValue === null
                    ? "no data"
                    : `${r.year} total: ${fmtCellValue(r.yearValue, metric)}`
                }
              >
                {fmtCellValue(r.yearValue, metric)}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
