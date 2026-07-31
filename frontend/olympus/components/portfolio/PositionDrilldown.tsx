'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { SegmentedControl } from '@digithings/web';
import { useAsyncData } from '@/lib/hooks/use-async-data';
import {
  AreaSeries,
  LineSeries,
  createSeriesMarkers,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts';
import { fetchPositionPriceChart } from '@/lib/queries';
import {
  buildDrilldownChartRows,
  buildPriceContributionPptSeries,
  closeOnOrAfter,
  computeAvgEntryFromAdds,
  defaultDrilldownWindow,
  DRILLDOWN_WINDOW_LABELS,
  filterActivityEvents,
  filterActivityEventsAscending,
  netWeightChangeFromChartRows,
  resolveDrilldownRange,
  resolveInceptionDate,
  type ContributionPptPoint,
  type DrilldownChartRow,
  type DrilldownWindow,
} from '@/lib/position-drilldown';
import type { DashboardPositionEvent, Position, PositionHistoryRow, Thesis } from '@/lib/types';
import { formatAllocationCategory } from '@/components/portfolio/tabs/palette-and-format';
import { normalizeThesisId } from '@/lib/thesis-id';
import { pnlColor } from '@/components/ui';
import { EVENT_COLORS, withAlpha } from '@/lib/chart-colors';
import { ChartTipShell, toLineData, useChartTip, useLightweightChart } from '@/lib/lw-chart';

function thesisNames(ids: string[], thesisById: Map<string, Thesis>): string {
  if (!ids.length) return '—';
  return ids.map((id) => thesisById.get(normalizeThesisId(id))?.name ?? id).join(', ');
}

// Fixed marker/label hues from the sanctioned allowlist (lib/chart-colors.ts) —
// ADD unifies with the sibling price/contribution charts' sky blue. Labels ride
// the SAME map as the markers (inline style, like performance-chart-workspace's
// tooltips): token-driven classes collapsed OPEN and ADD in dark mode, where
// --up === --accent, and disagreed with the marker hues on the same chart.
function eventMarkerColor(ev: DashboardPositionEvent['event']): string {
  if (ev === 'OPEN') return EVENT_COLORS.OPEN;
  if (ev === 'EXIT') return EVENT_COLORS.EXIT;
  if (ev === 'ADD') return EVENT_COLORS.ADD;
  if (ev === 'TRIM') return EVENT_COLORS.TRIM;
  return EVENT_COLORS.DEFAULT;
}

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Weight-% area (left scale) + close-$ line (right scale) with event dots — lightweight-charts (#1420). */
function DrilldownWeightPricePane({
  chartRows,
  markerPoints,
}: {
  chartRows: DrilldownChartRow[];
  markerPoints: Array<{ date: string; close: number; event: DashboardPositionEvent['event']; label: string }>;
}) {
  const { containerRef, chart, colors, isAlive } = useLightweightChart({
    leftPriceScale: { visible: true },
  });
  const tip = useChartTip(chart, containerRef, isAlive);
  const weightRef = useRef<ISeriesApi<'Area'> | null>(null);
  const priceRef = useRef<ISeriesApi<'Line'> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  const byDate = useMemo(() => new Map(chartRows.map((r) => [r.date, r])), [chartRows]);

  useEffect(() => {
    if (!chart || chartRows.length < 2) return;
    const weight = chart.addSeries(AreaSeries, {
      priceScaleId: 'left',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: { type: 'custom', formatter: (v: number) => `${v.toFixed(0)}%`, minMove: 0.01 },
    });
    weight.setData(toLineData(chartRows, (r) => r.date, (r) => r.weightPct));
    const price = chart.addSeries(LineSeries, {
      priceScaleId: 'right',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: { type: 'custom', formatter: (v: number) => `$${v.toFixed(0)}`, minMove: 0.01 },
    });
    price.setData(toLineData(chartRows, (r) => r.date, (r) => r.close));
    weightRef.current = weight;
    priceRef.current = price;
    markersRef.current = createSeriesMarkers(price, []);
    chart.timeScale().fitContent();
    return () => {
      weightRef.current = null;
      priceRef.current = null;
      markersRef.current = null;
      if (isAlive()) {
        chart.removeSeries(weight);
        chart.removeSeries(price);
      }
    };
  }, [chart, chartRows, isAlive]);

  // Token colors + event markers (re-applied on theme flips).
  useEffect(() => {
    weightRef.current?.applyOptions({
      lineColor: colors.accent,
      topColor: withAlpha(colors.accent, 0.25),
      bottomColor: withAlpha(colors.accent, 0),
    });
    priceRef.current?.applyOptions({ color: colors.accent });
    markersRef.current?.setMarkers(
      markerPoints.map(
        (m): SeriesMarker<Time> => ({
          time: m.date as Time,
          position: 'inBar',
          shape: 'circle',
          color: eventMarkerColor(m.event),
          size: 2,
        })
      )
    );
  }, [colors, chartRows, markerPoints]);

  const row = tip ? byDate.get(tip.iso) : undefined;

  return (
    <div ref={containerRef} className="relative h-full w-full">
      {tip && row ? (
        <ChartTipShell tip={tip}>
          <p className="font-mono text-ink-soft text-xs">{row.date}</p>
          <p className="text-ink tabular-nums mt-1">Close ${row.close.toFixed(2)}</p>
          <p className="text-ink-mute tabular-nums text-xs mt-0.5">Weight {row.weightPct.toFixed(2)}%</p>
          {row.dayEvents.length > 0 ? (
            <ul className="mt-2 space-y-1 text-xs">
              {row.dayEvents.map((ev, i) => (
                <li key={i} style={{ color: eventMarkerColor(ev.event) }}>
                  {ev.event}
                  {ev.weight_change_pct != null
                    ? ` · Δ ${ev.weight_change_pct >= 0 ? '+' : ''}${ev.weight_change_pct.toFixed(2)}pp`
                    : null}
                </li>
              ))}
            </ul>
          ) : null}
        </ChartTipShell>
      ) : null}
    </div>
  );
}

/** Cumulative contribution (ppt) mini pane — lightweight-charts (#1420). */
function DrilldownContributionPane({ series }: { series: ContributionPptPoint[] }) {
  const { containerRef, chart, colors, isAlive } = useLightweightChart();
  const tip = useChartTip(chart, containerRef, isAlive);
  const areaRef = useRef<ISeriesApi<'Area'> | null>(null);

  const byDate = useMemo(() => new Map(series.map((r) => [r.date, r])), [series]);

  useEffect(() => {
    if (!chart || series.length < 2) return;
    const area = chart.addSeries(AreaSeries, {
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: { type: 'custom', formatter: (v: number) => v.toFixed(3), minMove: 0.0001 },
    });
    area.setData(toLineData(series, (r) => r.date, (r) => r.cumPp));
    areaRef.current = area;
    chart.timeScale().fitContent();
    return () => {
      areaRef.current = null;
      if (isAlive()) chart.removeSeries(area);
    };
  }, [chart, series, isAlive]);

  useEffect(() => {
    areaRef.current?.applyOptions({
      lineColor: colors.up,
      topColor: withAlpha(colors.up, 0.2),
      bottomColor: withAlpha(colors.up, 0),
    });
  }, [colors, series]);

  const row = tip ? byDate.get(tip.iso) : undefined;

  return (
    <div ref={containerRef} className="relative h-full w-full">
      {tip && row ? (
        <ChartTipShell tip={tip}>
          <p className="font-mono text-ink-soft text-xs">{row.date}</p>
          <p className="text-ink tabular-nums mt-1">
            Cumulative: {row.cumPp >= 0 ? '+' : ''}
            {row.cumPp.toFixed(4)} ppt
          </p>
          <p className="text-ink-mute tabular-nums text-xs mt-0.5">
            Daily: {row.dailyPp >= 0 ? '+' : ''}
            {row.dailyPp.toFixed(4)} ppt
          </p>
        </ChartTipShell>
      ) : null}
    </div>
  );
}

type Props = {
  position: Position;
  positionEvents: DashboardPositionEvent[];
  positionHistory: PositionHistoryRow[];
  thesisById: Map<string, Thesis>;
  /** Portfolio snapshot date (Allocations) or performance anchor. */
  asOfDate: string | null;
  /** When set, clip the drilldown to the Performance tab range. */
  performanceRange?: { start: string; end: string } | null;
  mode: 'allocations' | 'performance';
};

export default function PositionDrilldown({
  position,
  positionEvents,
  positionHistory,
  thesisById,
  asOfDate,
  performanceRange,
  mode,
}: Props) {
  const displayEnd = performanceRange?.end ?? asOfDate ?? isoToday();
  const inceptionDate = useMemo(
    () => resolveInceptionDate(position.ticker, position, positionHistory, positionEvents),
    [position, positionHistory, positionEvents]
  );

  const defaultWindow = useMemo(
    () => defaultDrilldownWindow(inceptionDate, displayEnd),
    [inceptionDate, displayEnd]
  );
  const [userWindow, setUserWindow] = useState<DrilldownWindow | null>(null);
  const windowPreset = userWindow ?? defaultWindow;

  const { fetchFrom, displayStart, displayEnd: rangeEnd } = useMemo(
    () => resolveDrilldownRange(asOfDate ?? displayEnd, windowPreset, inceptionDate, performanceRange ?? null),
    [asOfDate, windowPreset, inceptionDate, performanceRange, displayEnd]
  );

  const emptyChart = { chartRows: [] as DrilldownChartRow[], priceSorted: [] as Array<{ date: string; close: number }> };
  const { loading, error: err, data: chartData } = useAsyncData(
    emptyChart,
    async () => {
      const d = await fetchPositionPriceChart(position.ticker, fetchFrom, rangeEnd);
      const sorted = [...(d.priceHistory ?? [])].sort((a, b) => a.date.localeCompare(b.date));
      const evAsc = filterActivityEventsAscending(positionEvents, position.ticker, displayStart, rangeEnd);
      const rows = buildDrilldownChartRows(sorted, positionHistory, position.ticker, displayStart, rangeEnd, evAsc);
      return { chartRows: rows, priceSorted: sorted };
    },
    [position.ticker, fetchFrom, rangeEnd, displayStart, positionHistory, positionEvents]
  );
  const { chartRows, priceSorted } = chartData;

  const openAddAsc = useMemo(() => {
    const all = filterActivityEventsAscending(
      positionEvents,
      position.ticker,
      '1970-01-01',
      rangeEnd
    ).filter((e) => e.event === 'OPEN' || e.event === 'ADD');
    return all;
  }, [positionEvents, position.ticker, rangeEnd]);

  const avgEntryComputed = useMemo(
    () => computeAvgEntryFromAdds(openAddAsc, priceSorted),
    [openAddAsc, priceSorted]
  );

  const avgEntry = avgEntryComputed ?? position.entry_price ?? null;
  const curr = position.current_price ?? null;
  const pnlVsAvg =
    avgEntry != null && curr != null && avgEntry > 0 ? ((curr - avgEntry) / avgEntry) * 100 : null;

  const netW = netWeightChangeFromChartRows(chartRows);

  const ledgerDesc = useMemo(
    () => filterActivityEvents(positionEvents, position.ticker, displayStart, rangeEnd),
    [positionEvents, position.ticker, displayStart, rangeEnd]
  );

  const contributionSeries = useMemo(() => {
    if (mode !== 'performance') return [];
    return buildPriceContributionPptSeries(priceSorted, positionHistory, position.ticker, displayStart, rangeEnd);
  }, [mode, priceSorted, positionHistory, position.ticker, displayStart, rangeEnd]);

  const periodContribPpt = contributionSeries.length
    ? contributionSeries[contributionSeries.length - 1].cumPp
    : null;

  const markerPoints = useMemo(() => {
    const pts: Array<{
      date: string;
      close: number;
      event: DashboardPositionEvent['event'];
      label: string;
    }> = [];
    for (const row of chartRows) {
      if (!row.dayEvents.length) continue;
      const primary = row.dayEvents[0];
      const label =
        row.dayEvents.length === 1
          ? primary.event
          : `${row.dayEvents.length} events`;
      pts.push({
        date: row.date,
        close: row.close,
        event: primary.event,
        label,
      });
    }
    return pts;
  }, [chartRows]);

  const onLedgerPrice = useCallback(
    (e: DashboardPositionEvent) => {
      if (e.price != null && !Number.isNaN(Number(e.price)) && Number(e.price) > 0) {
        return Number(e.price);
      }
      return closeOnOrAfter(priceSorted, e.date);
    },
    [priceSorted]
  );

  const windowOptions = (['1m', '3m', 'ytd', '1y', 'itd'] as const).map((value) => ({
    value,
    label: DRILLDOWN_WINDOW_LABELS[value],
  }));

  return (
    <div className="max-w-full min-w-0 space-y-5 border-l border-hair pl-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-semibold truncate">
            {position.ticker}
            {position.name ? <span className="text-ink-mute font-normal"> — {position.name}</span> : null}
          </p>
          <p className="text-xs text-ink-mute">
            As of {rangeEnd}
            {mode === 'performance' && performanceRange ? ` · Range ${performanceRange.start} → ${rangeEnd}` : null}
          </p>
        </div>
        <SegmentedControl<DrilldownWindow>
          options={windowOptions}
          value={windowPreset}
          onChange={setUserWindow}
          dress="accent"
          aria-label="Position history range"
        />
      </div>

      <div className="grid grid-cols-2 border-y border-hair md:grid-cols-4 lg:grid-cols-6">
        <div className="min-w-0 border-l border-hair px-3 py-3">
          <p className="text-xs font-semibold tracking-wide text-ink-mute">Weight</p>
          <p className="text-sm mt-1 font-mono tabular-nums">
            {position.weight_actual != null ? `${position.weight_actual.toFixed(1)}%` : '—'}
          </p>
        </div>
        <div className="min-w-0 border-l border-hair px-3 py-3">
          <p className="text-xs font-semibold tracking-wide text-ink-mute">Avg entry</p>
          <p className="text-sm mt-1 font-mono tabular-nums">
            {avgEntry != null ? `$${avgEntry.toFixed(2)}` : '—'}
          </p>
        </div>
        <div className="min-w-0 border-l border-hair px-3 py-3">
          <p className="text-xs font-semibold tracking-wide text-ink-mute">Unrealized</p>
          <p className={`text-sm mt-1 font-mono tabular-nums font-semibold ${pnlColor(pnlVsAvg)}`}>
            {pnlVsAvg != null ? `${pnlVsAvg >= 0 ? '+' : ''}${pnlVsAvg.toFixed(2)}%` : '—'}
          </p>
        </div>
        <div className="min-w-0 border-l border-hair px-3 py-3">
          <p className="text-xs font-semibold tracking-wide text-ink-mute">Δ weight (window)</p>
          <p className={`text-sm mt-1 font-mono tabular-nums ${pnlColor(netW)}`}>
            {netW != null ? `${netW >= 0 ? '+' : ''}${netW.toFixed(2)}pp` : '—'}
          </p>
        </div>
        <div className="col-span-2 min-w-0 border-l border-hair px-3 py-3 lg:col-span-2">
          <p className="text-xs font-semibold tracking-wide text-ink-mute">Category / thesis</p>
          <p className="text-sm mt-1 truncate">
            {formatAllocationCategory(position.category)} · {thesisNames(position.thesis_ids, thesisById)}
          </p>
        </div>
      </div>

      {mode === 'performance' && periodContribPpt != null && !Number.isNaN(periodContribPpt) ? (
        <div className="rounded-md border border-hair bg-bg/30 px-3 py-2 text-sm">
          <span className="text-ink-mute">Attributed contribution (window): </span>
          <span className={`font-mono tabular-nums font-semibold ${pnlColor(periodContribPpt)}`}>
            {periodContribPpt >= 0 ? '+' : ''}
            {periodContribPpt.toFixed(3)} ppt
          </span>
          <span className="text-ink-mute text-xs ml-2">(daily return × prior-day weight)</span>
        </div>
      ) : null}

      {loading ? (
        <p className="text-sm text-ink-mute py-6 text-center">Loading chart data…</p>
      ) : err ? (
        <p className="text-sm text-warn py-4">{err}</p>
      ) : chartRows.length >= 2 ? (
        <div className="space-y-2">
          <p className="text-xs font-semibold tracking-wide text-ink-mute">Weight &amp; price</p>
          <div className="h-[280px] w-full min-w-0">
            <DrilldownWeightPricePane chartRows={chartRows} markerPoints={markerPoints} />
          </div>
        </div>
      ) : (
        <p className="text-sm text-ink-mute py-2">
          Not enough price history in this window for the chart. See activity below.
        </p>
      )}

      {mode === 'performance' && contributionSeries.length >= 2 ? (
        <div className="space-y-2">
          <p className="text-xs font-semibold tracking-wide text-ink-mute">Cumulative contribution (ppt)</p>
          <div className="h-[160px] w-full min-w-0">
            <DrilldownContributionPane series={contributionSeries} />
          </div>
        </div>
      ) : null}

      <div className="space-y-2">
        <p className="text-xs font-semibold tracking-wide text-ink-mute">Activity</p>
        <div className="overflow-x-auto rounded-md border border-hair">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="text-left text-ink-mute text-xs uppercase tracking-wider border-b border-hair bg-bg/30">
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Action</th>
                <th className="px-3 py-2 text-right">Δ weight</th>
                <th className="px-3 py-2 text-right">Before → after</th>
                <th className="px-3 py-2 text-right">Price</th>
                <th className="px-3 py-2">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hair">
              {ledgerDesc.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-ink-mute text-sm">
                    No OPEN / ADD / TRIM / EXIT events in this window.
                  </td>
                </tr>
              ) : (
                ledgerDesc.map((e, i) => {
                  const ledgerPx = onLedgerPrice(e);
                  return (
                  <tr key={`${e.date}-${e.event}-${i}`} className="hover:bg-ink/[0.02]">
                    <td className="px-3 py-2 font-mono text-xs text-ink-soft whitespace-nowrap">{e.date}</td>
                    <td className="px-3 py-2">
                      <span className="font-semibold text-xs" style={{ color: eventMarkerColor(e.event) }}>
                        {e.event}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-xs">
                      {e.weight_change_pct != null
                        ? `${e.weight_change_pct >= 0 ? '+' : ''}${e.weight_change_pct.toFixed(2)}pp`
                        : '—'}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-xs text-ink-soft">
                      {e.prev_weight_pct != null && e.weight_pct != null
                        ? `${e.prev_weight_pct.toFixed(2)} → ${e.weight_pct.toFixed(2)}%`
                        : '—'}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-xs">
                      {ledgerPx != null ? `$${ledgerPx.toFixed(2)}` : '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-ink-mute max-w-[280px]">{e.reason ?? '—'}</td>
                  </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
