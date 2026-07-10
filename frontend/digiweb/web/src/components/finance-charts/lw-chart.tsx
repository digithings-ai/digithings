"use client";

/**
 * Lightweight-charts scaffold (#1450 batch E) — the persistent-chart
 * counterpart to `useFinanceChart` (chart-host.tsx), converged from the
 * olympus `lib/lw-chart.tsx` scaffold (#1420) so dashboards and display
 * surfaces share ONE canon. Two sanctioned lifecycles:
 *
 *   - `useFinanceChart` (chart-host.tsx) — setup-callback style; a data
 *     change tears the chart down and rebuilds it. Right for display
 *     specimens (PriceChart / EquityCurve / DrawdownPlot).
 *   - `useLightweightChart` (here) — the chart is exposed as state and
 *     persists across data changes; callers own their series in effects,
 *     guarding cleanup with `isAlive()`. Right for live dashboards
 *     (olympus portfolio surfaces, tearsheet workspaces).
 *
 * Both wear the same token chrome (`chartChromeOptions`), keep the canvas
 * transparent with the attribution logo off, disable kinetic-scroll inertia
 * under prefers-reduced-motion (the resting chart IS the final state), and
 * are SSR-safe — charts exist only after mount; hosts render as plain divs
 * with no JS. This module is palette-agnostic: the caller supplies resolved
 * token colors (olympus binds its ChartColors; package consumers pair it
 * with `useFinanceChartPalette()` from chart-host.tsx).
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
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
} from "lightweight-charts";

/* ── Theme surface ─────────────────────────────────────────────────────── */

/** The four resolved token values chart chrome is painted with. */
export type ChartChrome = {
  /** Axis text + crosshair line color — canon `--ink-mute`. */
  text: string;
  /** Grid lines + price/time scale borders — canon `--hair`. */
  hair: string;
  /** Crosshair label background — `--accent`, or a money token for P&L reads. */
  label: string;
  /** Axis font — canon `--font-mono` (see `hostMonoFont`). */
  fontFamily: string;
};

/**
 * Chart-wide options derived from the canon tokens: transparent canvas,
 * hair-token grid + scale borders (both price scales), mono axis text,
 * token-backed crosshair. Re-applied wholesale on theme flips.
 */
export function chartChromeOptions(chrome: ChartChrome): DeepPartial<ChartOptions> {
  return {
    layout: {
      background: { type: ColorType.Solid, color: "transparent" },
      textColor: chrome.text,
      fontFamily: chrome.fontFamily,
      fontSize: 11,
      attributionLogo: false,
    },
    grid: { vertLines: { color: chrome.hair }, horzLines: { color: chrome.hair } },
    rightPriceScale: { borderColor: chrome.hair },
    leftPriceScale: { borderColor: chrome.hair },
    timeScale: { borderColor: chrome.hair, timeVisible: false },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: chrome.text, labelBackgroundColor: chrome.label },
      horzLine: { color: chrome.text, labelBackgroundColor: chrome.label },
    },
  };
}

/** `--font-mono` read off the chart host (scoped overrides win), SSR-safe. */
export function hostMonoFont(host: HTMLElement | null): string {
  if (!host || typeof window === "undefined") return "monospace";
  return getComputedStyle(host).getPropertyValue("--font-mono").trim() || "monospace";
}

/* ── Chart lifecycle hook ──────────────────────────────────────────────── */

export interface UseLightweightChartResult<C> {
  /** Attach to the chart host div (make it `relative` when using tooltips). */
  containerRef: RefObject<HTMLDivElement | null>;
  /** Live chart instance — `null` on the server and until mount (SSR-safe). */
  chart: IChartApi | null;
  /** The theme-reactive colors passed in, echoed for destructuring. */
  colors: C;
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

export interface UseLightweightChartConfig<C> {
  /**
   * Resolved theme colors — a NEW identity re-applies the themed options,
   * so pass a per-theme-cached snapshot (`useFinanceChartPalette()` or an
   * app hook like olympus's `useChartColors()`), not a fresh object per
   * render.
   */
  colors: C;
  /** Colors + host element → chart chrome options (latest render wins). */
  buildOptions: (colors: C, host: HTMLElement | null) => DeepPartial<ChartOptions>;
  /**
   * Optional live read used once at chart creation (client-side), so the
   * first paint never wears an SSR-fallback palette. Defaults to the latest
   * `colors` value.
   */
  readColors?: () => C;
  /** Merged once at creation (first render wins). */
  extraOptions?: DeepPartial<ChartOptions>;
}

/**
 * Creates/destroys a lightweight-chart bound to `containerRef`: `autoSize`
 * on, token theme from `buildOptions`, options re-applied when `colors`
 * changes identity (theme flips), kinetic-scroll inertia disabled under
 * reduced motion. The chart persists across data changes — callers add and
 * remove their own series in effects, guarding cleanup with `isAlive()`.
 */
export function useLightweightChart<C>(
  config: UseLightweightChartConfig<C>
): UseLightweightChartResult<C> {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [chart, setChart] = useState<IChartApi | null>(null);
  const alive = useRef(false);
  const isAlive = useCallback(() => alive.current, []);
  const [reducedMotion] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true
  );
  const configRef = useRef(config);
  configRef.current = config;
  const extraRef = useRef(config.extraOptions);

  useEffect(() => {
    const host = containerRef.current;
    if (!host) return;
    const { buildOptions, readColors, colors } = configRef.current;
    const created = createChart(host, {
      autoSize: true,
      ...buildOptions(readColors ? readColors() : colors, host),
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

  // Theme-reactive: re-apply the token-derived options on theme flips.
  // Series colors are re-applied by callers (they own their series).
  useEffect(() => {
    if (!chart || !alive.current) return;
    chart.applyOptions(configRef.current.buildOptions(config.colors, containerRef.current));
  }, [chart, config.colors]);

  return { containerRef, chart, colors: config.colors, isAlive, reducedMotion };
}

/* ── Data adapters ─────────────────────────────────────────────────────── */

/**
 * Array-of-objects rows (recharts-shaped) → lightweight-charts line/area
 * points. `null`/`NaN` values become whitespace points, which render as
 * gaps — the recharts `connectNulls` look is intentionally NOT reproduced
 * for missing data inside a series (gaps are more honest). Rows must
 * already be ascending by ISO date.
 */
export function toLineData<T>(
  rows: readonly T[],
  getDate: (row: T) => string,
  getValue: (row: T) => number | null | undefined
): (LineData<Time> | WhitespaceData<Time>)[] {
  const out: (LineData<Time> | WhitespaceData<Time>)[] = [];
  let prev = "";
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
  if (typeof t === "string") return t;
  if (typeof t === "number") return new Date(t * 1000).toISOString().slice(0, 10);
  const mm = String(t.month).padStart(2, "0");
  const dd = String(t.day).padStart(2, "0");
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

/**
 * Token-styled floating tooltip chrome. Consuming apps must `@source` this
 * directory so the utility classes below are generated (MIGRATION.md rule 3).
 */
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
