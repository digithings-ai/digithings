'use client';

import { useEffect, useMemo, useRef } from 'react';
import { BaselineSeries, type ISeriesApi } from 'lightweight-charts';
import { useChartColors, withAlpha } from '@/lib/chart-colors';
import { ChartTipShell, toLineData, useChartTip, useLightweightChart } from '@/lib/lw-chart';

/**
 * Underwater (peak-to-trough) drawdown — lightweight-charts BaselineSeries,
 * mirroring the digiweb drawdown-plot-reference grammar (#1420).
 */
export function PerformanceDrawdownChart({
  data,
}: {
  data: Array<{ date: string; drawdown: number }>;
}) {
  const { containerRef, chart, colors, isAlive } = useLightweightChart();
  const seriesRef = useRef<ISeriesApi<'Baseline'> | null>(null);
  const tip = useChartTip(chart, containerRef, isAlive);

  const byDate = useMemo(() => new Map(data.map((d) => [d.date, d.drawdown])), [data]);

  // Series + data (recreated when the range changes).
  useEffect(() => {
    if (!chart || data.length < 2) return;
    const series = chart.addSeries(BaselineSeries, {
      baseValue: { type: 'price', price: 0 },
      topLineColor: 'transparent',
      topFillColor1: 'transparent',
      topFillColor2: 'transparent',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: {
        type: 'custom',
        formatter: (v: number) => `${v.toFixed(0)}%`,
        minMove: 0.01,
      },
    });
    series.setData(toLineData(data, (d) => d.date, (d) => d.drawdown));
    seriesRef.current = series;
    chart.timeScale().fitContent();
    return () => {
      seriesRef.current = null;
      if (isAlive()) chart.removeSeries(series);
    };
  }, [chart, data, isAlive]);

  // Token colors — applied after (re)creation and re-applied on theme flips.
  useEffect(() => {
    seriesRef.current?.applyOptions({
      bottomLineColor: colors.down,
      bottomFillColor1: withAlpha(colors.down, 0.05),
      bottomFillColor2: withAlpha(colors.down, 0.28),
    });
  }, [colors, data]);

  if (data.length < 2) {
    return (
      <div className="h-[240px] flex items-center justify-center text-ink-mute text-sm">
        Not enough NAV history for drawdown.
      </div>
    );
  }

  const tipValue = tip ? byDate.get(tip.iso) : undefined;

  return (
    <div ref={containerRef} className="relative h-full w-full">
      {tip && tipValue != null ? (
        <ChartTipShell tip={tip}>
          <p className="text-ink-soft text-[0.75rem] font-mono">{tip.iso}</p>
          <div className="flex justify-between gap-3 mt-0.5">
            <span className="text-ink-soft">Drawdown</span>
            <span className="font-mono tabular-nums text-ink">{tipValue.toFixed(2)}%</span>
          </div>
        </ChartTipShell>
      ) : null}
    </div>
  );
}
