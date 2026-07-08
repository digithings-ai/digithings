'use client';

import { useEffect, useMemo, useRef } from 'react';
import { LineSeries, type ISeriesApi } from 'lightweight-charts';
import type { NavChartPoint } from '@/lib/types';
import { computeRiskRatiosFromNavSnaps } from '@/lib/portfolio-risk-metrics';
import { ROLLING_SERIES } from '@/lib/chart-colors';
import { ChartTipShell, toLineData, useChartTip, useLightweightChart } from '@/lib/lw-chart';

function PeriodRiskSummary({
  sharpe,
  sortino,
  annVolPct,
}: {
  sharpe: number;
  sortino: number;
  annVolPct: number;
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 rounded-lg border border-hair bg-term-bg/50 p-4">
      <div>
        <p className="text-[10px] text-ink-mute uppercase tracking-wider mb-1">Sharpe (Rf = 0)</p>
        <p className="text-lg font-semibold tabular-nums text-ink">{sharpe.toFixed(2)}</p>
      </div>
      <div>
        <p className="text-[10px] text-ink-mute uppercase tracking-wider mb-1">Sortino</p>
        <p className="text-lg font-semibold tabular-nums text-ink">{sortino.toFixed(2)}</p>
      </div>
      <div>
        <p className="text-[10px] text-ink-mute uppercase tracking-wider mb-1">Ann. volatility</p>
        <p className="text-lg font-semibold tabular-nums text-ink">{annVolPct.toFixed(1)}%</p>
      </div>
    </div>
  );
}

type RollingPoint = { date: string; sharpe: number | null; volAnn: number | null };

/** Rolling Sharpe (left scale) vs annualized vol (right scale) — lightweight-charts (#1420). */
function RollingLinesChart({ data, rollingWindow }: { data: RollingPoint[]; rollingWindow: number }) {
  const { containerRef, chart, isAlive } = useLightweightChart({
    leftPriceScale: { visible: true },
  });
  const tip = useChartTip(chart, containerRef, isAlive);

  const byDate = useMemo(() => new Map(data.map((d) => [d.date, d])), [data]);

  useEffect(() => {
    if (!chart || !data.length) return;
    // Series hues are fixed identities from the sanctioned allowlist
    // (lib/chart-colors.ts ROLLING_SERIES) — no re-theme needed.
    const sharpe = chart.addSeries(LineSeries, {
      color: ROLLING_SERIES.sharpe,
      lineWidth: 2,
      priceScaleId: 'left',
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: { type: 'custom', formatter: (v: number) => v.toFixed(2), minMove: 0.01 },
    });
    const vol = chart.addSeries(LineSeries, {
      color: ROLLING_SERIES.vol,
      lineWidth: 1,
      priceScaleId: 'right',
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: { type: 'custom', formatter: (v: number) => `${v.toFixed(0)}%`, minMove: 0.01 },
    });
    sharpe.setData(toLineData(data, (d) => d.date, (d) => d.sharpe));
    vol.setData(toLineData(data, (d) => d.date, (d) => d.volAnn));
    chart.timeScale().fitContent();
    const series: ISeriesApi<'Line'>[] = [sharpe, vol];
    return () => {
      if (isAlive()) for (const s of series) chart.removeSeries(s);
    };
  }, [chart, data, isAlive]);

  const row = tip ? byDate.get(tip.iso) : undefined;

  return (
    <div className="h-full w-full flex flex-col gap-1.5">
      <div className="flex flex-wrap justify-end gap-x-4 gap-y-1 text-[11px] text-ink-soft pr-1">
        <span className="inline-flex items-center gap-1.5">
          <span
            className="w-3 h-0.5 rounded-full shrink-0"
            style={{ background: ROLLING_SERIES.sharpe }}
            aria-hidden
          />
          Rolling Sharpe ({rollingWindow}d)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            className="w-3 h-0.5 rounded-full shrink-0"
            style={{ background: ROLLING_SERIES.vol }}
            aria-hidden
          />
          Rolling vol (ann.)
        </span>
      </div>
      <div ref={containerRef} className="relative flex-1 min-h-0">
        {tip && row ? (
          <ChartTipShell tip={tip}>
            <p className="text-ink-soft text-[0.75rem] font-mono">{tip.iso}</p>
            <div className="flex justify-between gap-3 mt-0.5">
              <span className="text-ink-soft">Sharpe ({rollingWindow}d)</span>
              <span className="font-mono tabular-nums text-ink">
                {row.sharpe != null && !Number.isNaN(row.sharpe) ? row.sharpe.toFixed(2) : '—'}
              </span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-ink-soft">Vol (ann.)</span>
              <span className="font-mono tabular-nums text-ink">
                {row.volAnn != null && !Number.isNaN(row.volAnn) ? `${row.volAnn.toFixed(1)}%` : '—'}
              </span>
            </div>
          </ChartTipShell>
        ) : null}
      </div>
    </div>
  );
}

export function PerformanceRollingChart({
  data,
  snaps,
  rollingWindow,
}: {
  data: Array<{ date: string; sharpe: number | null; volAnn: number | null }>;
  snaps: NavChartPoint[];
  rollingWindow: number;
}) {
  const period = computeRiskRatiosFromNavSnaps(snaps);
  const hasRollingSharpe = data.some((d) => d.sharpe != null && !Number.isNaN(d.sharpe));
  const rollingPoints = data.filter((d) => d.sharpe != null && !Number.isNaN(d.sharpe)).length;

  return (
    <div className="space-y-4">
      {period ? (
        <>
          <PeriodRiskSummary sharpe={period.sharpe} sortino={period.sortino} annVolPct={period.annVolPct} />
          <p className="text-[11px] text-ink-mute leading-snug">
            Full selected range — same methodology as Advanced statistics (daily returns, Rf = 0).
          </p>
        </>
      ) : (
        <p className="text-sm text-ink-mute">Need at least two NAV observations in this range.</p>
      )}

      {hasRollingSharpe && rollingPoints >= 2 ? (
        <div className="space-y-2">
          <p className="text-[11px] text-ink-mute">
            Rolling series uses a {rollingWindow}-trading-day window (shortened automatically when history is
            limited).
          </p>
          <div className="h-[min(400px,50vh)] min-h-[280px] w-full">
            <RollingLinesChart data={data} rollingWindow={rollingWindow} />
          </div>
        </div>
      ) : period ? (
        <p className="text-[12px] text-ink-mute rounded-lg border border-dashed border-hair px-4 py-3">
          Not enough overlapping days in this range for rolling metrics.
        </p>
      ) : null}
    </div>
  );
}
