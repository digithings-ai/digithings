/**
 * Dependency-free SVG charts for strategy tearsheets (React port of the
 * standalone renderer). Pure vector output (no canvas, no libs) so the tearsheet
 * prints to PDF crisply. Charts render into a 0 0 1000 H viewBox and scale to the
 * container width. Colours come from CSS custom properties on the chart classes
 * (theme-aware via [data-theme]). Supports linear / log / symlog y scales —
 * symlog handles series that cross zero (cumulative P&L).
 */
import { type ReactNode, useEffect, useRef } from "react";
import { fmtCompact, fmtPct } from "./format";
import { type TearsheetPoint } from "./types";

const W = 1000;
const PAD = { top: 18, right: 26, bottom: 36, left: 84 };

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
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="ts-seg" role="group" aria-label={label}>
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
 * Translate a pointer event over a `viewBox 0 0 1000 H` SVG into a fraction
 * (0..1) across the chart's *plot area* (i.e. inside the left/right insets).
 * `padRight` differs per chart (ComboPnl uses a wider gutter), so callers pass it.
 */
function plotFraction(clientX: number, target: Element, padRight: number): number {
  const rect = target.getBoundingClientRect();
  if (rect.width === 0) return 0.5;
  // Fraction across the full 1000-unit viewBox width, then into plot coords.
  const x = ((clientX - rect.left) / rect.width) * W; // viewBox x
  const plotW = W - PAD.left - padRight;
  return Math.max(0, Math.min(1, (x - PAD.left) / plotW));
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
  padRight: number,
): ViewControl | null {
  if (!view || !onView) return null;
  const { lo, hi } = view;

  const onWheel = (clientX: number, deltaY: number, target: Element) => {
    const span = hi - lo;
    const cursor = lo + plotFraction(clientX, target, padRight) * span;
    // Wheel up (deltaY < 0) zooms in; down zooms out. Centred on the cursor.
    const factor = Math.exp(deltaY * 0.0015);
    const nlo = cursor - (cursor - lo) * factor;
    const nhi = cursor + (hi - cursor) * factor;
    onView(clampView(nlo, nhi));
  };

  const onMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    e.preventDefault();
    const startX = e.clientX;
    const span = hi - lo;
    const rect = e.currentTarget.getBoundingClientRect();
    const plotPxW = rect.width * ((W - PAD.left - padRight) / W);
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

  const onDoubleClick = () => onView({ lo: 0, hi: 1 });

  return { padRight, onWheel, onMouseDown, onDoubleClick };
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

function Svg({
  height,
  children,
  control,
}: {
  height: number;
  children: ReactNode;
  control?: ViewControl | null;
}) {
  const ref = useRef<SVGSVGElement>(null);
  // Attach wheel natively (non-passive) so preventDefault actually blocks page
  // scroll — React's synthetic onWheel is passive and cannot.
  useEffect(() => {
    const el = ref.current;
    if (!el || !control) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      control.onWheel(e.clientX, e.deltaY, el);
    };
    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  }, [control]);

  return (
    <svg
      ref={ref}
      viewBox={`0 0 ${W} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      className={"ts-svg" + (control ? " is-interactive" : "")}
      role="img"
      onMouseDown={control ? control.onMouseDown : undefined}
      onDoubleClick={control ? control.onDoubleClick : undefined}
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
  /** Shared normalized x-window (date span fraction). Omit ⇒ full range, static. */
  view?: ViewWindow;
  /** Notified on wheel-zoom / drag-pan / double-click reset. */
  onView?: (v: ViewWindow) => void;
  /** Full date span [firstISO, lastISO] for the *whole* series; defaults to the
   *  series' own endpoints. Pass the shared span so every chart maps the same
   *  fraction to the same calendar window even if point counts differ. */
  fullSpan?: [string, string];
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

/** Time-series area/line chart. */
export function TimeSeries({ points: allPoints, height = 320, scale: scaleKind = "linear", tone = "accent", fmt = fmtCompact, zeroBaseline = false, view, onView, fullSpan }: TimeSeriesProps) {
  if (!allPoints || allPoints.length === 0) return <Empty height={height} msg="no data" />;

  // Visible slice — the y-domain re-derives from the slice below, so x-zoom
  // intentionally auto-rescales the y-axis to the window's range.
  const points = sliceByView(allPoints, view, fullSpan);
  const control = viewHandlers(view, onView, PAD.right);
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
    <Svg height={height} control={control}>
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
  /** Per-trade P&L in dollars (left axis bars), in trade order. */
  pnl: number[];
  /** GLOBAL running cumulative P&L points (right axis line); same length / order
   *  as pnl, with `t` = each trade's exit date. */
  cumulative: TearsheetPoint[];
  initialCapital: number;
  scale: PnlScale;
  height?: number;
  /** Shared normalized x-window (date span fraction). Omit ⇒ full range, static. */
  view?: ViewWindow;
  onView?: (v: ViewWindow) => void;
  /** Shared full date span [firstISO, lastISO] — the equity-curve span, so the
   *  combo's trade window locks to the same calendar window as the line charts. */
  fullSpan?: [string, string];
}

/**
 * Dual-axis combo: per-trade P&L bars on the LEFT scale (gains up / losses down),
 * cumulative P&L as a line on its own RIGHT scale. The right scale toggles between
 * log dollars (symlog — legible across the strategy's many decades of compounding)
 * and cumulative return as a % of initial capital. Only the left/bars axis draws
 * gridlines; the right axis contributes labels only.
 *
 * When a `view` window is supplied, trades are filtered by their exit date to the
 * shared calendar window. The cumulative line keeps the GLOBAL running total at
 * each surviving index (not a window-local re-zero), so the line preserves its
 * real height and continuity within the window — it will only start at zero when
 * the window includes the very first trade.
 */
export function ComboPnl({ pnl: allPnl, cumulative: allCumulative, initialCapital, scale, height = 300, view, onView, fullSpan }: ComboPnlProps) {
  if (!allPnl || allPnl.length === 0) return <Empty height={height} msg="no trades" />;

  // Filter trades to the shared window by exit date (cumulative[i].t). The
  // surviving cumulative values stay on the GLOBAL running total — documented above.
  let pnl = allPnl;
  let cumulative = allCumulative;
  if (view && !(view.lo <= 0 && view.hi >= 1)) {
    const t0 = new Date((fullSpan ? fullSpan[0] : (allCumulative[0]?.t ?? ""))).getTime();
    const t1 = new Date((fullSpan ? fullSpan[1] : (allCumulative[allCumulative.length - 1]?.t ?? ""))).getTime();
    const span = t1 - t0;
    if (span > 0) {
      const loT = t0 + view.lo * span;
      const hiT = t0 + view.hi * span;
      const keepPnl: number[] = [];
      const keepCum: TearsheetPoint[] = [];
      allCumulative.forEach((p, i) => {
        const t = new Date(p.t).getTime();
        if (t >= loT && t <= hiT) {
          keepPnl.push(allPnl[i]);
          keepCum.push(p);
        }
      });
      if (keepCum.length > 0) {
        pnl = keepPnl;
        cumulative = keepCum;
      }
    }
  }

  const control = viewHandlers(view, onView, 60 /* PR below */);
  if (!pnl || pnl.length === 0) return <Empty height={height} msg="no trades in window" />;

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
    <Svg height={height} control={control}>
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

// ----------------------------- Returns matrix ------------------------------

export type ReturnsPeriod = "monthly" | "quarterly" | "annual";

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const QUARTER_LABELS = ["Q1", "Q2", "Q3", "Q4"];

/** A single rendered cell: the period return % (or null = no data in that slot). */
interface MatrixCell {
  ret: number | null;
}
interface MatrixRow {
  year: number;
  cells: MatrixCell[]; // one per column for the granularity
  yearRet: number | null; // trailing "Year" column (compounded)
}

/** Number of columns per granularity (the trailing Year column is separate). */
function colCount(period: ReturnsPeriod): number {
  return period === "monthly" ? 12 : period === "quarterly" ? 4 : 1;
}

/**
 * Reduce an equity curve to period-over-period returns. The "close" of a period
 * is its last sampled equity; the return is close / prevClose − 1, chained across
 * periods (so a flat-but-missing month inherits the previous close). The baseline
 * before the very first sampled period is the opening equity (equity_curve[0].v ≈
 * initial capital). Empty period slots stay null. The Year column compounds the
 * year's own first-to-last ratio (independent of granularity).
 */
function buildReturnsRows(points: TearsheetPoint[], period: ReturnsPeriod): MatrixRow[] {
  if (!points || points.length === 0) return [];
  const cols = colCount(period);
  const slotOf = (m: number) => (period === "monthly" ? m : period === "quarterly" ? Math.floor(m / 3) : 0);

  // Last sampled equity per (year, slot), plus per-year first/last for the Year col.
  const lastInSlot = new Map<string, number>(); // `${year}:${slot}` -> equity
  const yearFirst = new Map<number, number>();
  const yearLast = new Map<number, number>();
  let minYear = Infinity, maxYear = -Infinity;

  for (const p of points) {
    const d = new Date(p.t);
    const year = d.getUTCFullYear();
    const month = d.getUTCMonth();
    const slot = slotOf(month);
    lastInSlot.set(`${year}:${slot}`, p.v); // later points overwrite ⇒ last wins
    if (!yearFirst.has(year)) yearFirst.set(year, p.v);
    yearLast.set(year, p.v);
    if (year < minYear) minYear = year;
    if (year > maxYear) maxYear = year;
  }
  if (!Number.isFinite(minYear)) return [];

  const opening = points[0].v;
  const rows: MatrixRow[] = [];
  // prevClose chains across the *whole* timeline so a gap inherits the last close.
  let prevClose = opening;

  for (let year = minYear; year <= maxYear; year++) {
    const cells: MatrixCell[] = [];
    for (let s = 0; s < cols; s++) {
      const close = lastInSlot.get(`${year}:${s}`);
      if (close === undefined) {
        cells.push({ ret: null }); // no data in this period
      } else {
        const ret = prevClose > 0 ? (close / prevClose - 1) * 100 : null;
        cells.push({ ret });
        prevClose = close;
      }
    }
    // Year column: compound the year's own first→last ratio against the close
    // carried into the year (so the first year reflects growth from `opening`).
    const last = yearLast.get(year);
    const yearRet = last !== undefined && prevCloseAtYearStart(year, minYear, opening, yearLast) > 0
      ? (last / prevCloseAtYearStart(year, minYear, opening, yearLast) - 1) * 100
      : null;
    rows.push({ year, cells, yearRet });
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

/** Inline cell background: tone-coloured with alpha scaled by |return| relative to
 *  the granularity's max-abs (small floor so non-zero cells are always visible). */
function cellBg(ret: number | null, maxAbs: number): string {
  if (ret === null) return "transparent";
  if (ret === 0) return "transparent";
  const tone = ret > 0 ? "var(--up)" : "var(--down)";
  const mag = maxAbs > 0 ? Math.abs(ret) / maxAbs : 0;
  // 14%..72% alpha — readable text stays legible, strong months stand out.
  const pct = Math.round(14 + Math.min(1, mag) * 58);
  return `color-mix(in srgb, ${tone} ${pct}%, transparent)`;
}

/** Compact cell % — sheds decimals as magnitude grows so wide crypto returns
 *  (hundreds / thousands of %) fit the narrow grid cells without truncation. */
function fmtCellPct(v: number | null): string {
  if (v === null) return "";
  const a = Math.abs(v);
  if (a >= 1000) return fmtCompact(v) + "%"; // e.g. "1.3K%"
  if (a >= 100) return v.toFixed(0) + "%"; // e.g. "683%"
  return v.toFixed(1) + "%"; // e.g. "25.7%"
}

/**
 * Calendar heatmap of period returns derived from the equity curve. Rows = years,
 * columns = months / quarters / a single annual cell, plus a trailing compounded
 * "Year" column. Pure CSS-grid table (no SVG) so it reflows and scrolls on mobile.
 */
export function ReturnsMatrix({ points, period }: { points: TearsheetPoint[]; period: ReturnsPeriod }) {
  const rows = buildReturnsRows(points, period);
  if (rows.length === 0) return <div className="ts-status">no data</div>;

  const cols = colCount(period);
  const labels = period === "monthly" ? MONTH_LABELS : period === "quarterly" ? QUARTER_LABELS : ["Year"];
  // For the annual granularity the single column already IS the year return, so we
  // suppress the duplicate trailing Year column.
  const showYearCol = period !== "annual";

  // Max-abs across all rendered cell returns (incl. the Year column) for alpha scale.
  let maxAbs = 0;
  for (const r of rows) {
    for (const c of r.cells) if (c.ret !== null) maxAbs = Math.max(maxAbs, Math.abs(c.ret));
    if (showYearCol && r.yearRet !== null) maxAbs = Math.max(maxAbs, Math.abs(r.yearRet));
  }

  const totalCols = 1 + cols + (showYearCol ? 1 : 0); // year-label + data + Year
  const gridTemplate = `minmax(2.6rem, auto) repeat(${cols + (showYearCol ? 1 : 0)}, minmax(0, 1fr))`;

  const fmtCell = (v: number | null) => fmtCellPct(v);

  return (
    <div className="ts-table-wrap">
      <div className="ts-matrix" style={{ gridTemplateColumns: gridTemplate, minWidth: totalCols > 6 ? "640px" : undefined }} role="table" aria-label={`${period} returns`}>
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
                className={"ts-matrix-cell" + (c.ret === null ? " is-empty" : "")}
                style={{ background: cellBg(c.ret, maxAbs) }}
                role="cell"
                title={c.ret === null ? "no data" : `${labels[i]} ${r.year}: ${fmtPct(c.ret)}`}
              >
                {fmtCell(c.ret)}
              </div>
            ))}
            {showYearCol ? (
              <div
                className={"ts-matrix-cell ts-matrix-year" + (r.yearRet === null ? " is-empty" : "")}
                style={{ background: cellBg(r.yearRet, maxAbs) }}
                role="cell"
                title={r.yearRet === null ? "no data" : `${r.year} total: ${fmtPct(r.yearRet)}`}
              >
                {fmtCell(r.yearRet)}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
