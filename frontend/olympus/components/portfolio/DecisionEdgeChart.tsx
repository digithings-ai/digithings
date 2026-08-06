'use client';

import { useEffect, useMemo } from 'react';
import { LineSeries, type ISeriesApi } from 'lightweight-charts';
import {
  ChartTipShell,
  toLineData,
  useChartTip,
  useLightweightChart,
} from '@/lib/lw-chart';

export interface DecisionEdgePoint {
  date: string;
  value: number;
}

export default function DecisionEdgeChart({ points }: { points: DecisionEdgePoint[] }) {
  const { containerRef, chart, colors, isAlive } = useLightweightChart();
  const tip = useChartTip(chart, containerRef, isAlive);
  const byDate = useMemo(() => new Map(points.map((point) => [point.date, point])), [points]);

  useEffect(() => {
    if (!chart || points.length < 2) return;
    const series = chart.addSeries(LineSeries, {
      color: colors.accent,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      priceFormat: {
        type: 'custom',
        formatter: (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(2)}%`,
        minMove: 0.01,
      },
    });
    series.setData(toLineData(points, (point) => point.date, (point) => point.value));
    series.createPriceLine({
      price: 0,
      color: colors.hair,
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: false,
      title: '',
    });
    chart.timeScale().fitContent();
    const owned: ISeriesApi<'Line'> = series;
    return () => {
      if (isAlive()) chart.removeSeries(owned);
    };
  }, [chart, colors.accent, colors.hair, isAlive, points]);

  const point = tip ? byDate.get(tip.iso) : undefined;
  return (
    <div className="relative h-[260px] min-h-[260px] w-full">
      <div ref={containerRef} className="absolute inset-0" aria-label="Decision edge over time chart">
        {tip && point ? (
          <ChartTipShell tip={tip}>
            <p className="font-mono text-xs text-ink-soft">{tip.iso}</p>
            <div className="mt-1 flex justify-between gap-4 text-xs">
              <span className="text-ink-soft">Decision edge</span>
              <strong className="font-mono text-ink">
                {point.value > 0 ? '+' : ''}{point.value.toFixed(2)}%
              </strong>
            </div>
          </ChartTipShell>
        ) : null}
      </div>
    </div>
  );
}