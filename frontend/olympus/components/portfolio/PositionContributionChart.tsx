'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AreaSeries,
  LineStyle,
  createSeriesMarkers,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts';
import { fetchPositionPriceChart } from '@/lib/queries';
import { buildEventContributionSteps } from '@/lib/position-contribution-event-steps';
import { buildPositionContributionToNavSeries, type PositionContributionPoint } from '@/lib/position-contribution-series';
import type { NavChartPoint, PositionHistoryRow, PositionPriceChartData, PositionPriceChartEvent } from '@/lib/types';
import { EVENT_COLORS, useChartColors, withAlpha } from '@/lib/chart-colors';
import { ChartTipShell, toLineData, useChartTip, useLightweightChart } from '@/lib/lw-chart';
import { PositionContributionEventBars, type EventBarDatum } from './PositionContributionEventBars';

function subtractIsoDays(iso: string, days: number): string {
  const parts = iso.split('-').map(Number);
  if (parts.length < 3) return iso;
  const [y, m, d] = parts;
  const t = Date.UTC(y, m - 1, d);
  const next = new Date(t - days * 86400000);
  return next.toISOString().slice(0, 10);
}

const ENTRY_PADDING_DAYS = 45;
const FALLBACK_LOOKBACK_DAYS = 730;

function eventDotColor(ev: PositionPriceChartEvent['event']): string {
  // Fixed marker hues from the sanctioned allowlist (lib/chart-colors.ts).
  if (ev === 'OPEN') return EVENT_COLORS.OPEN;
  if (ev === 'EXIT') return EVENT_COLORS.EXIT;
  if (ev === 'ADD') return EVENT_COLORS.ADD;
  if (ev === 'TRIM') return EVENT_COLORS.TRIM;
  return EVENT_COLORS.DEFAULT;
}

function eventLabelClass(ev: PositionPriceChartEvent['event']): string {
  if (ev === 'OPEN') return 'text-up';
  if (ev === 'EXIT') return 'text-down';
  if (ev === 'ADD') return 'text-accent';
  if (ev === 'TRIM') return 'text-warn';
  return 'text-ink-mute';
}

function rowOnOrAfter(rows: PositionContributionPoint[], iso: string): PositionContributionPoint | null {
  const exact = rows.find((r) => r.date === iso);
  if (exact) return exact;
  return rows.find((r) => r.date >= iso) ?? null;
}

/** An OPEN/EXIT/ADD/TRIM event snapped onto its (on-or-after) series day. */
type EventMarkerRow = PositionContributionPoint & {
  event: PositionPriceChartEvent['event'];
  markPrice: number | null;
  weight_pct: number | null;
  prev_weight_pct: number | null;
  weight_change_pct: number | null;
  reason: string | null;
};

function ContribChartPanel({
  ticker,
  rangeLabel,
  chartRows,
  closeByDate,
  events,
  firstEntryDate,
  eventBarData,
  contribTickDecimals,
}: {
  ticker: string;
  rangeLabel: string;
  chartRows: PositionContributionPoint[];
  closeByDate: Map<string, number>;
  events: PositionPriceChartEvent[];
  firstEntryDate: string | null;
  eventBarData: EventBarDatum[];
  contribTickDecimals: number;
}) {
  const { containerRef, chart, colors, isAlive } = useLightweightChart();
  const tip = useChartTip(chart, containerRef, isAlive);
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null);
  const zeroLineRef = useRef<IPriceLine | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  const byDate = useMemo(() => new Map(chartRows.map((r) => [r.date, r])), [chartRows]);

  const markers = useMemo(() => {
    const evs = events.filter((e) => e.event !== 'HOLD');
    if (!chartRows.length) return [] as EventMarkerRow[];
    const first = chartRows[0].date;
    const last = chartRows[chartRows.length - 1].date;
    return evs
      .filter((e) => e.date >= first && e.date <= last)
      .map((ev): EventMarkerRow | null => {
        const tr = rowOnOrAfter(chartRows, ev.date);
        if (!tr) return null;
        return {
          ...tr,
          event: ev.event,
          markPrice: ev.price,
          weight_pct: ev.weight_pct,
          prev_weight_pct: ev.prev_weight_pct,
          weight_change_pct: ev.weight_change_pct,
          reason: ev.reason,
        };
      })
      .filter((x): x is EventMarkerRow => x != null)
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [events, chartRows]);

  const entryLineDate = useMemo(() => {
    if (!firstEntryDate || !chartRows.length) return null;
    if (firstEntryDate < chartRows[0].date || firstEntryDate > chartRows[chartRows.length - 1].date) {
      return null;
    }
    return rowOnOrAfter(chartRows, firstEntryDate)?.date ?? null;
  }, [firstEntryDate, chartRows]);

  // Cumulative-ppt series + data.
  useEffect(() => {
    if (!chart || !chartRows.length) return;
    const series = chart.addSeries(AreaSeries, {
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: {
        type: 'custom',
        formatter: (v: number) => v.toFixed(contribTickDecimals),
        minMove: 0.0001,
      },
    });
    series.setData(toLineData(chartRows, (r) => r.date, (r) => r.cumPp));
    seriesRef.current = series;
    markersRef.current = createSeriesMarkers(series, []);
    zeroLineRef.current = series.createPriceLine({
      price: 0,
      lineStyle: LineStyle.Dashed,
      lineWidth: 1,
      axisLabelVisible: false,
      color: withAlpha(colors.ink, 0.12),
    });
    chart.timeScale().fitContent();
    return () => {
      seriesRef.current = null;
      markersRef.current = null;
      zeroLineRef.current = null;
      if (isAlive()) chart.removeSeries(series);
    };
    // colors is applied by the effect below; recreate only on data changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chart, chartRows, contribTickDecimals, isAlive]);

  // Token colors + event/entry markers (re-applied on theme flips).
  useEffect(() => {
    seriesRef.current?.applyOptions({
      lineColor: colors.accent,
      topColor: withAlpha(colors.accent, 0.35),
      bottomColor: withAlpha(colors.accent, 0),
    });
    zeroLineRef.current?.applyOptions({ color: withAlpha(colors.ink, 0.12) });
    const marks: SeriesMarker<Time>[] = [];
    if (entryLineDate) {
      marks.push({
        time: entryLineDate as Time,
        position: 'belowBar',
        shape: 'arrowUp',
        color: withAlpha(colors.up, 0.65),
        text: 'Entry',
        size: 1,
      });
    }
    markers.forEach((m, i) => {
      marks.push({
        time: m.date as Time,
        position: 'inBar',
        shape: 'circle',
        color: eventDotColor(m.event),
        size: m.event === 'TRIM' || m.event === 'ADD' ? 1 : 2,
        id: `evt:${i}`,
      });
    });
    marks.sort((a, b) => String(a.time).localeCompare(String(b.time)));
    markersRef.current?.setMarkers(marks);
  }, [colors, chartRows, markers, entryLineDate]);

  const fitAll = useCallback(() => {
    chart?.timeScale().fitContent();
  }, [chart]);

  const chartEnd = chartRows[chartRows.length - 1].date;

  const hoveredMarker = useMemo(() => {
    const id = tip?.param.hoveredObjectId;
    if (typeof id !== 'string' || !id.startsWith('evt:')) return null;
    return markers[Number(id.slice(4))] ?? null;
  }, [tip, markers]);

  const tipRow = tip ? byDate.get(tip.iso) : undefined;
  const tipClose = tip ? closeByDate.get(tip.iso) : undefined;

  return (
    <div className="rounded-xl border border-hair bg-term-bg/20 overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-2 px-4 pt-3 pb-1">
        <div>
          <p className="text-[11px] text-ink-mute uppercase tracking-wider">Contribution to portfolio</p>
          <p className="text-sm font-medium text-ink mt-0.5">
            <span className="font-mono text-accent">{ticker}</span>
            <span className="text-ink-mute font-normal"> · </span>
            <span className="text-ink-soft text-xs font-mono">{rangeLabel}</span>
          </p>
          <p className="text-[10px] text-ink-mute mt-1 font-mono">
            {chartRows[0].date} → {chartEnd} · ppt (portfolio)
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <button
            type="button"
            onClick={fitAll}
            className="text-[11px] px-2.5 py-1 rounded-lg border border-hair text-ink-soft hover:bg-ink/[0.04] hover:text-ink transition-colors"
          >
            Fit all
          </button>
          <p className="text-[10px] text-ink-mute">Drag to pan · scroll to zoom</p>
        </div>
      </div>

      <div className="h-[min(360px,46vh)] min-h-[240px] w-full px-2 pb-3">
        <div ref={containerRef} className="relative h-full w-full">
          {tip && hoveredMarker ? (
            <ChartTipShell tip={tip}>
              <p className={`font-mono font-semibold ${eventLabelClass(hoveredMarker.event)}`}>
                {hoveredMarker.event}
              </p>
              <p className="text-ink-soft mt-1 font-mono">{hoveredMarker.date}</p>
              <p className="text-ink tabular-nums mt-0.5">
                Cumulative: {hoveredMarker.cumPp.toFixed(3)} ppt
              </p>
              {closeByDate.get(hoveredMarker.date) != null ? (
                <p className="text-ink-mute tabular-nums text-[11px] mt-1">
                  Close (proxy day): ${closeByDate.get(hoveredMarker.date)?.toFixed(2)}
                </p>
              ) : null}
              {hoveredMarker.weight_pct != null ? (
                <p className="text-ink-mute mt-1 tabular-nums">
                  Weight after: {hoveredMarker.weight_pct.toFixed(2)}%
                </p>
              ) : null}
              {hoveredMarker.reason ? (
                <p className="text-ink-mute mt-1.5 text-[11px] leading-snug">{hoveredMarker.reason}</p>
              ) : null}
            </ChartTipShell>
          ) : tip && tipRow ? (
            <ChartTipShell tip={tip}>
              <p className="font-mono text-ink-soft">{tipRow.date}</p>
              <p className="text-ink tabular-nums mt-0.5">Cumulative: {tipRow.cumPp.toFixed(3)} ppt</p>
              <p className="text-ink-mute tabular-nums text-[11px] mt-1">Step: {tipRow.dailyPp.toFixed(4)} ppt</p>
              {tipClose != null ? (
                <p className="text-ink-mute tabular-nums text-[11px] mt-1">Close: ${tipClose.toFixed(2)}</p>
              ) : null}
            </ChartTipShell>
          ) : null}
        </div>
      </div>

      <PositionContributionEventBars data={eventBarData} tickDecimals={contribTickDecimals} />
    </div>
  );
}

function ChartBody({
  ticker,
  rangeStart,
  rangeLabel,
  firstEntryDate,
  navSnaps,
  positionHistory,
  anchorDate,
  navWindowStart,
}: {
  ticker: string;
  rangeStart: string;
  rangeLabel: string;
  firstEntryDate: string | null;
  navSnaps: NavChartPoint[];
  positionHistory: PositionHistoryRow[];
  anchorDate: string;
  /** When set (Performance tab range), NAV contribution starts here instead of entry−pad. */
  navWindowStart?: string | null;
}) {
  const chart = useChartColors();
  const [data, setData] = useState<PositionPriceChartData | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    /* Cap at anchor so price/events match the performance as-of window (not wall-clock today). */
    fetchPositionPriceChart(ticker, rangeStart, anchorDate)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) {
          setData(null);
          setErr(e instanceof Error ? e.message : 'Failed to load chart');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, rangeStart, anchorDate]);

  /** Align NAV steps with the Performance date-range picker (1M / 3M / YTD / ITD). */
  const effectiveNavStart = useMemo(() => {
    if (navWindowStart && navWindowStart > rangeStart) return navWindowStart;
    return rangeStart;
  }, [navWindowStart, rangeStart]);

  const chartRows = useMemo<PositionContributionPoint[]>(() => {
    if (!data?.priceHistory?.length) return [];
    const navFiltered = navSnaps
      .filter((s) => s.date >= effectiveNavStart && s.date <= anchorDate)
      .sort((a, b) => a.date.localeCompare(b.date));
    return buildPositionContributionToNavSeries(
      navFiltered,
      positionHistory,
      ticker,
      data.priceHistory.map((p) => ({ date: p.date, close: p.close }))
    );
  }, [data, navSnaps, positionHistory, ticker, effectiveNavStart, anchorDate]);

  const closeByDate = useMemo(() => {
    const m = new Map<string, number>();
    for (const row of data?.priceHistory ?? []) {
      m.set(row.date, row.close);
    }
    return m;
  }, [data?.priceHistory]);

  const contribTickDecimals = useMemo(() => {
    if (!chartRows.length) return 2;
    let lo = Infinity;
    let hi = -Infinity;
    for (const r of chartRows) {
      lo = Math.min(lo, r.cumPp);
      hi = Math.max(hi, r.cumPp);
    }
    const span = hi - lo;
    if (span < 0.05) return 3;
    if (span < 0.4) return 2;
    return 1;
  }, [chartRows]);

  const eventStepRows = useMemo(() => {
    return buildEventContributionSteps(chartRows, data?.events ?? []);
  }, [chartRows, data?.events]);

  const eventBarData = useMemo<EventBarDatum[]>(() => {
    return eventStepRows.map((s) => ({
      name:
        s.kind === 'tail' && s.label.length > 42 ? `${s.label.slice(0, 40)}…` : s.label,
      deltaPp: s.deltaPp,
      fill: s.deltaPp >= 0 ? withAlpha(chart.up, 0.75) : withAlpha(chart.down, 0.75),
    }));
  }, [eventStepRows, chart]);

  if (loading) {
    return (
      <div className="h-[240px] rounded-xl border border-hair bg-term-bg/30 animate-pulse flex items-center justify-center text-xs text-ink-mute">
        Loading series…
      </div>
    );
  }
  if (err) {
    return (
      <div className="h-[200px] rounded-xl border border-hair bg-term-bg/30 flex items-center justify-center text-xs text-down px-4 text-center">
        {err}
      </div>
    );
  }
  if (!chartRows.length) {
    return (
      <div className="h-[160px] rounded-xl border border-hair bg-term-bg/30 flex items-center justify-center text-xs text-ink-mute px-4 text-center">
        Not enough overlapping NAV steps and price history to plot contribution.
      </div>
    );
  }

  return (
    <ContribChartPanel
      key={chartRows.length}
      ticker={ticker}
      rangeLabel={rangeLabel}
      chartRows={chartRows}
      closeByDate={closeByDate}
      events={data?.events ?? []}
      firstEntryDate={firstEntryDate}
      eventBarData={eventBarData}
      contribTickDecimals={contribTickDecimals}
    />
  );
}

export default function PositionContributionChart({
  ticker,
  anchorDate,
  firstEntryDate,
  navSnaps,
  positionHistory,
  navWindowStart,
}: {
  ticker: string;
  anchorDate: string;
  firstEntryDate?: string | null;
  navSnaps: NavChartPoint[];
  positionHistory: PositionHistoryRow[];
  navWindowStart?: string | null;
}) {
  const rangeStart = useMemo(() => {
    if (firstEntryDate) return subtractIsoDays(firstEntryDate, ENTRY_PADDING_DAYS);
    return subtractIsoDays(anchorDate, FALLBACK_LOOKBACK_DAYS);
  }, [firstEntryDate, anchorDate]);

  const rangeLabel = useMemo(() => {
    const base = firstEntryDate
      ? `Since first activity (−${ENTRY_PADDING_DAYS}d pad)`
      : `${FALLBACK_LOOKBACK_DAYS}d lookback`;
    if (navWindowStart && navWindowStart > rangeStart) return `${base} · NAV from range start`;
    return base;
  }, [firstEntryDate, navWindowStart, rangeStart]);

  return (
    <ChartBody
      key={`${ticker}|${rangeStart}|${anchorDate}|${navWindowStart ?? ''}|contrib`}
      ticker={ticker}
      rangeStart={rangeStart}
      rangeLabel={rangeLabel}
      firstEntryDate={firstEntryDate ?? null}
      navSnaps={navSnaps}
      positionHistory={positionHistory}
      anchorDate={anchorDate}
      navWindowStart={navWindowStart ?? null}
    />
  );
}
