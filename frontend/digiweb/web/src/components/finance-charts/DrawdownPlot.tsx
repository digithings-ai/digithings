"use client";

/**
 * DrawdownPlot — the underwater curve promoted from the design reference
 * (finance/drawdown): percent below the running peak as a baseline series on
 * TradingView Lightweight Charts, hanging under a zero baseline. It only
 * ever reads negative, so it takes the `--down` money color — the depth and
 * duration of the red is the risk story the CAGR hides. Re-themes live on
 * `data-theme` flips.
 *
 * Data comes in via the required `data` prop (ISO-dated points, ascending,
 * every value ≤ 0); `DRAWDOWN_DEMO` is the exported reference filler. The
 * host fills its pane (`autoSize`) — give the pane a definite height.
 * Client component — chart lifecycle effect; no motion/react surface.
 *
 * Wiring (consuming app): `lightweight-charts` dependency, plus
 *   globals.css   @source "<path-to>/digiweb/web/src/components/finance-charts";
 */

import { useCallback } from "react";
import { BaselineSeries, type BaselineData, type IChartApi } from "lightweight-charts";
import {
  toChartTime,
  tokenAlpha,
  useFinanceChart,
  type FinanceChartPalette,
  type FinanceSeriesPoint,
} from "./chart-host";

export type DrawdownPlotProps = {
  /** Drawdown-% series (values ≤ 0), ISO `yyyy-mm-dd` ascending. */
  data: FinanceSeriesPoint[];
  /** Extra classes on the chart host (it is `h-full w-full` by default). */
  className?: string;
  /** Accessible name; omitted → decorative (`aria-hidden`). */
  label?: string;
};

export function DrawdownPlot({ data, className, label }: DrawdownPlotProps) {
  const setup = useCallback(
    (chart: IChartApi, p: FinanceChartPalette) => {
      const series = chart.addSeries(BaselineSeries, {
        baseValue: { type: "price", price: 0 },
        topLineColor: "transparent",
        topFillColor1: "transparent",
        topFillColor2: "transparent",
        bottomLineColor: p.down,
        bottomFillColor1: tokenAlpha(p.down, 0.05),
        bottomFillColor2: tokenAlpha(p.down, 0.32),
        lineWidth: 2,
        priceLineVisible: false,
      });
      series.setData(
        data.map((pt): BaselineData => ({ time: toChartTime(pt.time), value: pt.value }))
      );
      return (next: FinanceChartPalette) => {
        series.applyOptions({
          bottomLineColor: next.down,
          bottomFillColor1: tokenAlpha(next.down, 0.05),
          bottomFillColor2: tokenAlpha(next.down, 0.32),
        });
      };
    },
    [data]
  );

  const hostRef = useFinanceChart(setup, "down");

  return (
    <div
      ref={hostRef}
      className={`h-full w-full${className ? ` ${className}` : ""}`}
      {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })}
    />
  );
}
