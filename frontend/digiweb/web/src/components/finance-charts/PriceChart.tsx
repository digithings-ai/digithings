"use client";

/**
 * PriceChart — the standard price-plotting primitive promoted from the design
 * reference (finance/price-chart): candlesticks (plus an optional volume
 * histogram tucked under the price pane) on TradingView Lightweight Charts.
 * Candles wear the `--up`/`--down` money colors — this IS a P&L read — the
 * volume wears the hairline token, and everything re-themes live on
 * `data-theme` flips. Custom SVG candles are retired (see the finance
 * reference page's charting rules).
 *
 * Data comes in via the required `candles` prop (ISO-dated OHLC, ascending);
 * `volume` is optional — omit it for a candles-only pane. `PRICE_CHART_DEMO`
 * is the exported reference filler carrying both. The host fills its pane
 * (`autoSize`) — give the pane a definite height. Client component — chart
 * lifecycle effect; no motion/react surface.
 *
 * Wiring (consuming app): `lightweight-charts` dependency, plus
 *   globals.css   @source "<path-to>/digiweb/web/src/components/finance-charts";
 */

import { useCallback } from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
} from "lightweight-charts";
import {
  toChartTime,
  useFinanceChart,
  type FinanceChartPalette,
  type FinanceSeriesPoint,
  type OhlcPoint,
} from "./chart-host";

export type PriceChartProps = {
  /** OHLC candles, ISO `yyyy-mm-dd` ascending. */
  candles: OhlcPoint[];
  /** Optional volume bars (same time axis); omitted → candles only. */
  volume?: FinanceSeriesPoint[];
  /** Extra classes on the chart host (it is `h-full w-full` by default). */
  className?: string;
  /** Accessible name; omitted → decorative (`aria-hidden`). */
  label?: string;
};

export function PriceChart({ candles, volume, className, label }: PriceChartProps) {
  const setup = useCallback(
    (chart: IChartApi, p: FinanceChartPalette) => {
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: p.up,
        downColor: p.down,
        borderUpColor: p.up,
        borderDownColor: p.down,
        wickUpColor: p.up,
        wickDownColor: p.down,
      });
      candleSeries.setData(
        candles.map(
          (c): CandlestickData => ({
            time: toChartTime(c.time),
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
          })
        )
      );

      const volumeSeries = volume
        ? chart.addSeries(HistogramSeries, {
            priceFormat: { type: "volume" },
            priceScaleId: "vol",
            color: p.hair,
          })
        : null;
      if (volumeSeries && volume) {
        volumeSeries.setData(
          volume.map((v): HistogramData => ({ time: toChartTime(v.time), value: v.value }))
        );
        chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      }

      return (next: FinanceChartPalette) => {
        candleSeries.applyOptions({
          upColor: next.up,
          downColor: next.down,
          borderUpColor: next.up,
          borderDownColor: next.down,
          wickUpColor: next.up,
          wickDownColor: next.down,
        });
        volumeSeries?.applyOptions({ color: next.hair });
      };
    },
    [candles, volume]
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
