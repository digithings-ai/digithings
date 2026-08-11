"use client";

/**
 * Finance-charts host scaffold (#1450) — the family's shared TradingView
 * Lightweight Charts lifecycle, promoted from the design reference
 * (finance/price-chart · equity-curve · drawdown). Since batch E this IS the
 * chart-scaffold canon: olympus's `lib/lw-chart.tsx` is a thin adapter over
 * this family (see lw-chart.tsx here for the persistent-chart lifecycle).
 * Token-themed via CSS-variable reads with SSR fallbacks, `autoSize: true`,
 * transparent canvas, attribution logo off, a MutationObserver on
 * `data-theme` re-applies the palette live, and kinetic-scroll inertia is
 * disabled under prefers-reduced-motion.
 *
 * Charts draw on canvas, so there is no CSS file for them — the host div
 * carries `h-full w-full` utilities and fills whatever definite-height pane
 * the consumer provides. `lightweight-charts` must be a dependency of the
 * consuming app (it is a peer of this family).
 */

import { useEffect, useRef, useSyncExternalStore, type RefObject } from "react";
import {
  createChart,
  type ChartOptions,
  type DeepPartial,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import { chartChromeOptions } from "./lw-chart";

/** ISO-dated series point — the wire shape every finance chart accepts. */
export type FinanceSeriesPoint = {
  /** ISO `yyyy-mm-dd`, ascending and unique across the series. */
  time: string;
  value: number;
};

/** ISO-dated OHLC candle for <PriceChart/>. */
export type OhlcPoint = {
  /** ISO `yyyy-mm-dd`, ascending and unique across the series. */
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

/** Resolved design tokens a finance chart paints with. */
export type FinanceChartPalette = {
  ink: string;
  inkMute: string;
  hair: string;
  accent: string;
  up: string;
  down: string;
  mono: string;
};

/** Which palette token backs the crosshair's axis labels. */
export type CrosshairLabelToken = "accent" | "up" | "down";

/** ISO `yyyy-mm-dd` → lightweight-charts `Time`. */
export function toChartTime(iso: string): Time {
  return iso as unknown as Time;
}

/** Token reads off the host element, with SSR-safe fallbacks mirroring the
 *  dark theme in @digithings/design/tokens.css (the sanctioned cssVar
 *  fallback pattern — see scripts/check_frontend_canon.py). Pass `null`
 *  (or call on the server) to get the fallback palette verbatim. */
export function readFinancePalette(host: HTMLElement | null): FinanceChartPalette {
  const cs = host && typeof window !== "undefined" ? getComputedStyle(host) : null;
  const cssVar = (name: string, fallback: string) =>
    cs?.getPropertyValue(name).trim() || fallback;
  return {
    ink: cssVar("--ink", "#ECEEF0"),
    inkMute: cssVar("--ink-mute", "#8A9097"),
    hair: cssVar("--hair", "rgba(255,255,255,0.1)"),
    accent: cssVar("--accent", "#3dd6c4"),
    up: cssVar("--up", "#3FB984"),
    down: cssVar("--down", "#E0654B"),
    mono: cssVar("--font-mono", "monospace"),
  };
}

/**
 * Re-emit a resolved token color at `alpha` — the gradient fills read the
 * accent/money tokens, then thin them out. Handles both token spellings in
 * tokens.css: `#rgb`/`#rrggbb` hex (accents, money colors) and `rgb()`/
 * `rgba()` functions (hairlines). Unparseable values pass through.
 */
export function tokenAlpha(color: string, alpha: number): string {
  if (color.startsWith("#")) {
    const hex = color.slice(1);
    const full =
      hex.length === 3 || hex.length === 4
        ? [...hex.slice(0, 3)].map((c) => c + c).join("")
        : hex.slice(0, 6);
    if (!/^[0-9a-fA-F]{6}$/.test(full)) return color;
    const r = parseInt(full.slice(0, 2), 16);
    const g = parseInt(full.slice(2, 4), 16);
    const b = parseInt(full.slice(4, 6), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }
  const channels = color.match(/[\d.]+/g);
  if (!channels || channels.length < 3) return color;
  return `rgba(${channels[0]},${channels[1]},${channels[2]},${alpha})`;
}

/** Chart-wide options derived from the tokens: transparent canvas, hair
 *  grid + scale borders, ink-mute mono text and crosshair lines, token-backed
 *  crosshair labels. Re-applied wholesale on theme flips. Thin binding of the
 *  palette onto the family's unified chrome builder (lw-chart.tsx). */
export function financeChartOptions(
  p: FinanceChartPalette,
  crosshairLabel: CrosshairLabelToken
): DeepPartial<ChartOptions> {
  return chartChromeOptions({
    text: p.inkMute,
    hair: p.hair,
    label: p[crosshairLabel],
    fontFamily: p.mono,
  });
}

/* ── Theme-reactive document-level palette ─────────────────────────────── */

/** SSR / pre-mount snapshot — the fallback palette, referentially stable. */
const SSR_PALETTE = readFinancePalette(null);

let paletteCache: { theme: string | null; palette: FinanceChartPalette } | null = null;

/**
 * Resolved document-level palette, re-read once per `data-theme` flip and
 * referentially stable between flips (safe as an effect dependency). This is
 * the live-read companion to `useFinanceChartPalette` — pass it as
 * `readColors` when composing with `useLightweightChart`.
 */
export function getFinancePalette(): FinanceChartPalette {
  if (typeof window === "undefined") return SSR_PALETTE;
  const theme = document.documentElement.getAttribute("data-theme");
  if (!paletteCache || paletteCache.theme !== theme) {
    paletteCache = { theme, palette: readFinancePalette(document.documentElement) };
  }
  return paletteCache.palette;
}

function subscribeToThemeFlips(onStoreChange: () => void): () => void {
  const observer = new MutationObserver(onStoreChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => observer.disconnect();
}

/**
 * Theme-reactive palette hook: serves the fallback palette on the server
 * (hydration-safe), the live document-level token values on the client, and
 * re-reads when `data-theme` flips on `<html>`. Pairs with the persistent
 * `useLightweightChart` scaffold (lw-chart.tsx) for dashboard surfaces.
 * Note: document-level reads — scoped liveries (`.accent-digiquant { … }`)
 * resolve per-host only through `useFinanceChart`'s host reads.
 */
export function useFinanceChartPalette(): FinanceChartPalette {
  return useSyncExternalStore(subscribeToThemeFlips, getFinancePalette, () => SSR_PALETTE);
}

/**
 * Owns a chart's lifecycle against the returned host ref: create with the
 * token theme, hand the chart to `setup` (add series + set data there, return
 * a re-tint callback for the series' own colors), fit content, re-theme on
 * `data-theme` flips, dispose on unmount.
 *
 * `setup` is an effect dependency — memoize it with `useCallback` keyed on
 * the data props. A data change tears the chart down and rebuilds it, which
 * matches the reference specimens' lifecycle (these are display surfaces;
 * dashboards with live-updating series should use the persistent
 * `useLightweightChart` scaffold from lw-chart.tsx instead).
 */
export function useFinanceChart(
  setup: (
    chart: IChartApi,
    palette: FinanceChartPalette
  ) => (palette: FinanceChartPalette) => void,
  crosshairLabel: CrosshairLabelToken = "accent"
): RefObject<HTMLDivElement | null> {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const reducedMotion =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
    let palette = readFinancePalette(host);

    const chart: IChartApi = createChart(host, {
      autoSize: true,
      ...financeChartOptions(palette, crosshairLabel),
      // Reduced motion: no kinetic-scroll inertia (the final state is the
      // same chart — panning still works, it just stops with the pointer).
      ...(reducedMotion ? { kineticScroll: { touch: false, mouse: false } } : {}),
    });

    const retintSeries = setup(chart, palette);
    chart.timeScale().fitContent();

    const retheme = () => {
      palette = readFinancePalette(host);
      chart.applyOptions(financeChartOptions(palette, crosshairLabel));
      retintSeries(palette);
    };
    const themeObs = new MutationObserver(retheme);
    themeObs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    return () => {
      themeObs.disconnect();
      chart.remove();
    };
  }, [setup, crosshairLabel]);

  return hostRef;
}
