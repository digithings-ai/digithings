'use client';

/**
 * Shared TradingView Lightweight Charts scaffold — a thin adapter over the
 * @digithings/web finance-charts scaffold (#1450 batch E; the app-local
 * #1420 copy was promoted there verbatim). The lifecycle hook, the data
 * adapters and the crosshair-tooltip plumbing are the package's; what stays
 * olympus-local is the ChartColors binding — every color still flows from
 * lib/chart-colors.ts (the single sanctioned color source, #1402), so charts
 * re-skin with the theme exactly like the DOM does.
 *
 * The six chart surfaces keep importing from `@/lib/lw-chart` (guarded by
 * lib/lw-chart-canon.test.ts) and are behavior-identical to the #1420 shape.
 *
 * See lib/CHARTS.md for the engine ruling (lightweight-charts = time-series
 * canon; recharts stays for categorical/composition surfaces).
 */

import type { ChartOptions, DeepPartial } from 'lightweight-charts';
import {
  chartChromeOptions,
  hostMonoFont,
  useLightweightChart as useLwChartScaffold,
  type UseLightweightChartResult as LwScaffoldResult,
} from '@digithings/web';
import { getChartColors, useChartColors, type ChartColors } from '@/lib/chart-colors';

/* Package plumbing re-exported under the olympus API. ChartTipShell's utility
   classes are generated via the `@source` line in app/globals.css. */
export {
  ChartTipShell,
  timeToISO,
  toLineData,
  useChartTip,
  type ChartTip,
} from '@digithings/web';

/**
 * Chart-wide options derived from the canon tokens: transparent canvas,
 * hair-token grid + scale borders, ink-mute text/crosshair, accent crosshair
 * labels. Re-applied wholesale on theme flips. Thin binding of ChartColors
 * onto the package's unified chrome builder.
 */
export function themedChartOptions(
  colors: ChartColors,
  fontFamily: string
): DeepPartial<ChartOptions> {
  return chartChromeOptions({
    text: colors.axis,
    hair: colors.hair,
    label: colors.accent,
    fontFamily,
  });
}

/** The package scaffold result bound to olympus's ChartColors. */
export type UseLightweightChartResult = LwScaffoldResult<ChartColors>;

/**
 * Creates/destroys a lightweight-chart bound to `containerRef`:
 * `autoSize` on, token theme from `useChartColors()`, options re-applied when
 * the theme flips, kinetic-scroll inertia disabled under reduced motion.
 * `extraOptions` are merged once at creation (first render wins).
 */
export function useLightweightChart(
  extraOptions?: DeepPartial<ChartOptions>
): UseLightweightChartResult {
  const colors = useChartColors();
  return useLwChartScaffold<ChartColors>({
    colors,
    readColors: getChartColors,
    buildOptions: (c, host) => themedChartOptions(c, hostMonoFont(host)),
    extraOptions,
  });
}
