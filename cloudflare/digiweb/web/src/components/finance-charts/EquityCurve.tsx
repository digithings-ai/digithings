"use client";

/**
 * EquityCurve — the tearsheet's headline promoted from the design reference
 * (finance/equity-curve): cumulative equity as an area series on TradingView
 * Lightweight Charts. It wears the module accent — identity, not a single
 * P&L read, so the money colors stay out of it — with a gradient fill that
 * thins toward the baseline, and re-themes live on `data-theme` flips.
 *
 * Data comes in via the required `data` prop (ISO-dated points, ascending);
 * `EQUITY_CURVE_DEMO` is the exported reference filler. The host fills its
 * pane (`autoSize`) — give the pane a definite height. Client component —
 * chart lifecycle effect; no motion/react surface.
 *
 * Wiring (consuming app): `lightweight-charts` dependency, plus
 *   globals.css   @source "<path-to>/digiweb/web/src/components/finance-charts";
 */

import { useCallback } from "react";
import { AreaSeries, type AreaData, type IChartApi } from "lightweight-charts";
import {
  toChartTime,
  tokenAlpha,
  useFinanceChart,
  type FinanceChartPalette,
  type FinanceSeriesPoint,
} from "./chart-host";

export type EquityCurveProps = {
  /** Cumulative-equity series, ISO `yyyy-mm-dd` ascending. */
  data: FinanceSeriesPoint[];
  /** Extra classes on the chart host (it is `h-full w-full` by default). */
  className?: string;
  /** Accessible name; omitted → decorative (`aria-hidden`). */
  label?: string;
};

export function EquityCurve({ data, className, label }: EquityCurveProps) {
  const setup = useCallback(
    (chart: IChartApi, p: FinanceChartPalette) => {
      const area = chart.addSeries(AreaSeries, {
        lineColor: p.accent,
        topColor: tokenAlpha(p.accent, 0.28),
        bottomColor: tokenAlpha(p.accent, 0.02),
        lineWidth: 2,
        priceLineVisible: false,
      });
      area.setData(
        data.map((pt): AreaData => ({ time: toChartTime(pt.time), value: pt.value }))
      );
      return (next: FinanceChartPalette) => {
        area.applyOptions({
          lineColor: next.accent,
          topColor: tokenAlpha(next.accent, 0.28),
          bottomColor: tokenAlpha(next.accent, 0.02),
        });
      };
    },
    [data]
  );

  const hostRef = useFinanceChart(setup, "accent");

  return (
    <div
      ref={hostRef}
      className={`h-full w-full${className ? ` ${className}` : ""}`}
      {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })}
    />
  );
}
