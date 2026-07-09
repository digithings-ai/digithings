'use client';

/**
 * Shared TradingView Lightweight Charts scaffold (#1420, epic #1414).
 *
 * The house grammar mirrors the digiweb design reference
 * (equity-curve-reference.tsx / drawdown-plot-reference.tsx): token-themed,
 * `autoSize: true`, transparent background, no custom renderers. Every color
 * flows from lib/chart-colors.ts — the single sanctioned color source — so
 * charts re-skin with the theme exactly like the DOM does.
 *
 * See lib/CHARTS.md for the engine ruling (lightweight-charts = time-series
 * canon; recharts stays for categorical/composition surfaces).
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react';
import {
  ColorType,
  createChart,
  CrosshairMode,
  type ChartOptions,
  type DeepPartial,
  type IChartApi,
  type LineData,
  type MouseEventParams,
  type Time,
  type WhitespaceData,
} from 'lightweight-charts';
import { getChartColors, useChartColors, type ChartColors } from '@/lib/chart-colors';

/* ── Theme surface ─────────────────────────────────────────────────────── */

/**
 * Chart-wide options derived from the canon tokens: transparent canvas,
 * hair-token grid + scale borders, ink-mute text/crosshair, accent crosshair
 * labels. Re-applied wholesale on theme flips.
 */
export function themedChartOptions(
  colors: ChartColors,
  fontFamily: string
): DeepPartial<ChartOptions> {
  return {
    layout: {
      background: { type: ColorType.Solid, color: 'transparent' },
      textColor: colors.axis,
      fontFamily,
      fontSize: 11,
      attributionLogo: false,
    },
    grid: { vertLines: { color: colors.hair }, horzLines: { color: colors.hair } },
    rightPriceScale: { borderColor: colors.hair },
    leftPriceScale: { borderColor: colors.hair },
    timeScale: { borderColor: colors.hair, timeVisible: false },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: colors.axis, labelBackgroundColor: colors.accent },
      horzLine: { color: colors.axis, labelBackgroundColor: colors.accent },
    },
  };
}

function hostMonoFont(host: HTMLElement | null): string {
  if (!host || typeof window === 'undefined') return 'monospace';
  return getComputedStyle(host).getPropertyValue('--font-mono').trim() || 'monospace';
}

/* ── Chart lifecycle hook ──────────────────────────────────────────────── */

export interface UseLightweightChartResult {
  /** Attach to the chart host div (make it `relative` when using tooltips). */
  containerRef: RefObject<HTMLDivElement | null>;
  /** Live chart instance — `null` on the server and until mount (SSR-safe). */
  chart: IChartApi | null;
  /** Theme-reactive resolved token colors (re-renders on data-theme flips). */
  colors: ChartColors;
  /**
   * Returns false once the chart has been disposed. Series-owning effects
   * must guard their cleanup with this: React may run the hook's unmount
   * cleanup (`chart.remove()`) before a later-declared effect's cleanup.
   * Stable identity — safe in dependency arrays.
   */
  isAlive: () => boolean;
  /** prefers-reduced-motion, read at mount. */
  reducedMotion: boolean;
}

/**
 * Creates/destroys a lightweight-chart bound to `containerRef`:
 * `autoSize` on, token theme from `useChartColors()`, options re-applied when
 * the theme flips, kinetic-scroll inertia disabled under reduced motion.
 * `extraOptions` are merged once at creation (first render wins).
 */
export function useLightweightChart(
  extraOptions?: DeepPartial<ChartOptions>
): UseLightweightChartResult {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [chart, setChart] = useState<IChartApi | null>(null);
  const colors = useChartColors();
  const alive = useRef(false);
  const isAlive = useCallback(() => alive.current, []);
  const [reducedMotion] = useState(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
  );
  const extraRef = useRef(extraOptions);

  useEffect(() => {
    const host = containerRef.current;
    if (!host) return;
    const created = createChart(host, {
      autoSize: true,
      ...themedChartOptions(getChartColors(), hostMonoFont(host)),
      ...(reducedMotion ? { kineticScroll: { touch: false, mouse: false } } : {}),
      ...(extraRef.current ?? {}),
    });
    alive.current = true;
    setChart(created);
    return () => {
      alive.current = false;
      created.remove();
      setChart(null);
    };
  }, [reducedMotion]);

  // Theme-reactive: re-apply the token-derived options on data-theme flips.
  // Series colors are re-applied by callers (they own their series).
  useEffect(() => {
    if (!chart || !alive.current) return;
    chart.applyOptions(themedChartOptions(colors, hostMonoFont(containerRef.current)));
  }, [chart, colors]);

  return { containerRef, chart, colors, isAlive, reducedMotion };
}

/* ── Data adapters ─────────────────────────────────────────────────────── */

/**
 * recharts array-of-objects → lightweight-charts line/area points.
 * `null`/`NaN` values become whitespace points, which render as gaps —
 * the recharts `connectNulls` look is intentionally NOT reproduced for
 * missing data inside a series (gaps are more honest).
 * Rows must already be ascending by ISO date (all olympus series are).
 */
export function toLineData<T>(
  rows: readonly T[],
  getDate: (row: T) => string,
  getValue: (row: T) => number | null | undefined
): (LineData<Time> | WhitespaceData<Time>)[] {
  const out: (LineData<Time> | WhitespaceData<Time>)[] = [];
  let prev = '';
  for (const row of rows) {
    const date = getDate(row);
    if (!date || date === prev) continue; // lightweight-charts requires unique ascending times
    prev = date;
    const value = getValue(row);
    const time = date as Time;
    out.push(value == null || Number.isNaN(value) ? { time } : { time, value });
  }
  return out;
}

/** Crosshair `Time` (string | BusinessDay | UTC seconds) → ISO `yyyy-mm-dd`. */
export function timeToISO(t: Time): string {
  if (typeof t === 'string') return t;
  if (typeof t === 'number') return new Date(t * 1000).toISOString().slice(0, 10);
  const mm = String(t.month).padStart(2, '0');
  const dd = String(t.day).padStart(2, '0');
  return `${t.year}-${mm}-${dd}`;
}

/* ── Crosshair tooltip ─────────────────────────────────────────────────── */

export interface ChartTip {
  /** Clamped position inside the chart host, px. */
  left: number;
  top: number;
  /** ISO date under the crosshair. */
  iso: string;
  /** Raw crosshair params — read series values via `param.seriesData`. */
  param: MouseEventParams<Time>;
}

const TIP_WIDTH_GUESS = 240;
const TIP_OFFSET = 14;

/**
 * Subscribes to crosshair moves and yields a clamped tooltip anchor + params,
 * or `null` when the pointer is off the pane. Render your own token-styled
 * DOM tooltip from it (the house idiom — see ChartTipShell).
 */
export function useChartTip(
  chart: IChartApi | null,
  containerRef: RefObject<HTMLDivElement | null>,
  isAlive: () => boolean
): ChartTip | null {
  const [tip, setTip] = useState<ChartTip | null>(null);

  useEffect(() => {
    if (!chart) return;
    const onMove = (param: MouseEventParams<Time>) => {
      const host = containerRef.current;
      if (
        !host ||
        !param.point ||
        param.time == null ||
        param.point.x < 0 ||
        param.point.y < 0
      ) {
        setTip((old) => (old === null ? old : null));
        return;
      }
      const width = host.clientWidth;
      const flip = param.point.x > width - (TIP_WIDTH_GUESS + TIP_OFFSET);
      const left = flip
        ? Math.max(0, param.point.x - TIP_WIDTH_GUESS - TIP_OFFSET)
        : param.point.x + TIP_OFFSET;
      const top = Math.max(8, Math.min(param.point.y + TIP_OFFSET, host.clientHeight - 48));
      setTip({ left, top, iso: timeToISO(param.time), param });
    };
    chart.subscribeCrosshairMove(onMove);
    return () => {
      if (isAlive()) chart.unsubscribeCrosshairMove(onMove);
    };
  }, [chart, containerRef, isAlive]);

  return tip;
}

/** Token-styled floating tooltip chrome shared by the migrated charts. */
export function ChartTipShell({ tip, children }: { tip: ChartTip; children: ReactNode }) {
  return (
    <div
      className="pointer-events-none absolute z-10 rounded-lg border border-hair bg-term-bg px-3 py-2 text-[0.82rem] shadow-lg max-w-[240px]"
      style={{ left: tip.left, top: tip.top }}
    >
      {children}
    </div>
  );
}
