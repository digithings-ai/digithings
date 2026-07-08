'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AreaSeries,
  createSeriesMarkers,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts';
import { fetchPositionPriceChart } from '@/lib/queries';
import type { PositionHistoryRow, PositionPriceChartData, PositionPriceChartEvent } from '@/lib/types';
import { EVENT_COLORS, withAlpha } from '@/lib/chart-colors';
import { ChartTipShell, toLineData, useChartTip, useLightweightChart } from '@/lib/lw-chart';

function eventDotColor(ev: PositionPriceChartEvent['event']): string {
  // Fixed marker hues from the sanctioned allowlist (lib/chart-colors.ts).
  if (ev === 'OPEN') return EVENT_COLORS.OPEN;
  if (ev === 'EXIT') return EVENT_COLORS.EXIT;
  if (ev === 'ADD') return EVENT_COLORS.ADD;
  if (ev === 'TRIM') return EVENT_COLORS.TRIM;
  return EVENT_COLORS.DEFAULT;
}

function subtractIsoDays(iso: string, days: number): string {
  const parts = iso.split('-').map(Number);
  if (parts.length < 3) return iso;
  const [y, m, d] = parts;
  const t = Date.UTC(y, m - 1, d);
  const next = new Date(t - days * 86400000);
  return next.toISOString().slice(0, 10);
}

type Row = { date: string; close: number; is_trading_day: boolean };

function rowOnOrAfter(rows: Row[], iso: string): Row | null {
  const exact = rows.find((r) => r.date === iso);
  if (exact) return exact;
  return rows.find((r) => r.date >= iso) ?? null;
}

/** Calendar days before first entry to include as context. */
const ENTRY_PADDING_DAYS = 45;
/** When we cannot infer an entry, load ~2y of history. */
const FALLBACK_LOOKBACK_DAYS = 730;

/** An OPEN/EXIT/ADD/TRIM event snapped onto its (on-or-after) trading day. */
type EventMarkerRow = {
  date: string;
  close: number;
  event: PositionPriceChartEvent['event'];
  markPrice: number | null;
  weight_pct: number | null;
  prev_weight_pct: number | null;
  weight_change_pct: number | null;
  reason: string | null;
};

function PriceChartPanel({
  ticker,
  rangeLabel,
  chartRows,
  weightByDate,
  events,
  firstEntryDate,
}: {
  ticker: string;
  rangeLabel: string;
  chartRows: Row[];
  weightByDate: Map<string, number>;
  events: PositionPriceChartEvent[];
  firstEntryDate: string | null;
}) {
  const { containerRef, chart, colors, isAlive } = useLightweightChart();
  const tip = useChartTip(chart, containerRef, isAlive);
  const priceRef = useRef<ISeriesApi<'Area'> | null>(null);
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
          date: tr.date,
          close: tr.close,
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

  // Price series + data.
  useEffect(() => {
    if (!chart || !chartRows.length) return;
    const price = chart.addSeries(AreaSeries, {
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: { type: 'custom', formatter: (v: number) => v.toFixed(0), minMove: 0.01 },
    });
    price.setData(toLineData(chartRows, (r) => r.date, (r) => r.close));
    priceRef.current = price;
    markersRef.current = createSeriesMarkers(price, []);
    chart.timeScale().fitContent();
    return () => {
      priceRef.current = null;
      markersRef.current = null;
      if (isAlive()) chart.removeSeries(price);
    };
  }, [chart, chartRows, isAlive]);

  // Token colors + event/entry markers (re-applied on theme flips).
  useEffect(() => {
    priceRef.current?.applyOptions({
      lineColor: colors.accent,
      topColor: withAlpha(colors.accent, 0.35),
      bottomColor: withAlpha(colors.accent, 0),
    });
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

  /** Marker under the pointer, if any (hoveredObjectId carries our `evt:<i>` id). */
  const hoveredMarker = useMemo(() => {
    const id = tip?.param.hoveredObjectId;
    if (typeof id !== 'string' || !id.startsWith('evt:')) return null;
    return markers[Number(id.slice(4))] ?? null;
  }, [tip, markers]);

  const tipRow = tip ? byDate.get(tip.iso) : undefined;
  const tipWeight = tip ? weightByDate.get(tip.iso) : undefined;

  return (
    <div className="rounded-xl border border-hair bg-term-bg/20 overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-2 px-4 pt-3 pb-1">
        <div>
          <p className="text-[11px] text-ink-mute uppercase tracking-wider">Price</p>
          <p className="text-sm font-medium text-ink mt-0.5">
            <span className="font-mono text-accent">{ticker}</span>
            <span className="text-ink-mute font-normal"> · </span>
            <span className="text-ink-soft text-xs font-mono">{rangeLabel}</span>
          </p>
          <p className="text-[10px] text-ink-mute mt-1 font-mono">
            {chartRows[0].date} → {chartEnd}
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
              <p className="font-mono font-semibold" style={{ color: eventDotColor(hoveredMarker.event) }}>
                {hoveredMarker.event}
              </p>
              <p className="text-ink-soft mt-1 font-mono">{hoveredMarker.date}</p>
              <p className="text-ink-soft tabular-nums mt-0.5">
                Price:{' '}
                {hoveredMarker.markPrice != null
                  ? `$${hoveredMarker.markPrice.toFixed(2)}`
                  : `$${hoveredMarker.close.toFixed(2)}`}
              </p>
              {hoveredMarker.weight_pct != null ? (
                <p className="text-ink-mute mt-1 tabular-nums">
                  Weight after: {hoveredMarker.weight_pct.toFixed(2)}%
                </p>
              ) : null}
              {hoveredMarker.weight_change_pct != null ? (
                <p className="text-ink-mute tabular-nums">
                  Δ weight: {hoveredMarker.weight_change_pct > 0 ? '+' : ''}
                  {hoveredMarker.weight_change_pct.toFixed(2)}pp
                </p>
              ) : null}
              {hoveredMarker.reason ? (
                <p className="text-ink-mute mt-1.5 text-[11px] leading-snug">{hoveredMarker.reason}</p>
              ) : null}
            </ChartTipShell>
          ) : tip && tipRow ? (
            <ChartTipShell tip={tip}>
              <p className="font-mono text-ink-soft">{tipRow.date}</p>
              <p className="text-ink tabular-nums mt-0.5">${tipRow.close.toFixed(2)}</p>
              {typeof tipWeight === 'number' ? (
                <p className="text-ink-mute tabular-nums mt-1 text-[11px]">
                  Weight (portfolio): {tipWeight.toFixed(2)}%
                </p>
              ) : null}
            </ChartTipShell>
          ) : null}
        </div>
      </div>

      {markers.length > 0 ? (
        <div className="flex flex-wrap gap-x-3 gap-y-1 px-4 pb-3 text-[10px] text-ink-mute">
          {(['OPEN', 'ADD', 'TRIM', 'EXIT'] as const)
            .filter((ev) => markers.some((m) => m.event === ev))
            .map((ev) => (
              <span key={ev} className="inline-flex items-center gap-1">
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ background: eventDotColor(ev), boxShadow: `0 0 0 1.5px ${colors.bg}` }}
                  aria-hidden
                />
                {ev}
              </span>
            ))}
        </div>
      ) : null}
    </div>
  );
}

function ChartBody({
  ticker,
  rangeStart,
  rangeLabel,
  firstEntryDate,
  positionHistory,
  maxDate,
}: {
  ticker: string;
  rangeStart: string;
  rangeLabel: string;
  firstEntryDate: string | null;
  positionHistory?: PositionHistoryRow[] | null;
  /** Cap price/events at portfolio snapshot (or performance range); avoids UTC "today" vs DB mismatch. */
  maxDate?: string | null;
}) {
  const [data, setData] = useState<PositionPriceChartData | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPositionPriceChart(ticker, rangeStart, maxDate ?? undefined)
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
  }, [ticker, rangeStart, maxDate]);

  const chartRows = useMemo<Row[]>(() => {
    if (!data?.priceHistory?.length) return [];
    return data.priceHistory.map((p) => ({
      date: p.date,
      close: p.close,
      is_trading_day: p.is_trading_day,
    }));
  }, [data]);

  /** Forward-filled weight % for each price row (from rebalance snapshots in position_history). */
  const weightByDate = useMemo(() => {
    const m = new Map<string, number>();
    if (!positionHistory?.length || !chartRows.length) return m;
    const t = ticker.toUpperCase();
    const rows = positionHistory
      .filter((r) => String(r.ticker || '').toUpperCase() === t)
      .sort((a, b) => a.date.localeCompare(b.date));
    if (!rows.length) return m;
    let i = 0;
    let last: number | null = null;
    for (const row of chartRows) {
      while (i < rows.length && rows[i].date <= row.date) {
        last = rows[i].weight_pct;
        i++;
      }
      if (last != null) m.set(row.date, last);
    }
    return m;
  }, [positionHistory, ticker, chartRows]);

  if (loading) {
    return (
      <div className="h-[240px] rounded-xl border border-hair bg-term-bg/30 animate-pulse flex items-center justify-center text-xs text-ink-mute">
        Loading price history…
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
      <div className="h-[160px] rounded-xl border border-hair bg-term-bg/30 flex items-center justify-center text-xs text-ink-mute">
        No price history for this range.
      </div>
    );
  }

  return (
    <PriceChartPanel
      key={chartRows.length}
      ticker={ticker}
      rangeLabel={rangeLabel}
      chartRows={chartRows}
      weightByDate={weightByDate}
      events={data?.events ?? []}
      firstEntryDate={firstEntryDate}
    />
  );
}

export default function PositionPriceChart({
  ticker,
  anchorDate,
  firstEntryDate,
  positionHistory,
  maxDate,
}: {
  ticker: string;
  anchorDate: string;
  /** When set, fetch starts before this date (padding) so the window centers on position life. */
  firstEntryDate?: string | null;
  /** Optional: forward-filled weights on the daily price tooltip. */
  positionHistory?: PositionHistoryRow[] | null;
  /** Inclusive end date for prices (e.g. snapshot `last_updated`). Defaults to UTC today if omitted. */
  maxDate?: string | null;
}) {
  const rangeStart = useMemo(() => {
    if (firstEntryDate) return subtractIsoDays(firstEntryDate, ENTRY_PADDING_DAYS);
    return subtractIsoDays(anchorDate, FALLBACK_LOOKBACK_DAYS);
  }, [firstEntryDate, anchorDate]);

  const rangeLabel = useMemo(() => {
    if (firstEntryDate) return `Since first activity (−${ENTRY_PADDING_DAYS}d pad)`;
    return `${FALLBACK_LOOKBACK_DAYS}d lookback`;
  }, [firstEntryDate]);

  return (
    <ChartBody
      key={`${ticker}|${rangeStart}|${maxDate ?? ''}`}
      ticker={ticker}
      rangeStart={rangeStart}
      rangeLabel={rangeLabel}
      firstEntryDate={firstEntryDate ?? null}
      positionHistory={positionHistory}
      maxDate={maxDate}
    />
  );
}
