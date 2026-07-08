'use client';

import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useBrushRange } from '@/lib/hooks/use-brush-range';
import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchPositionPriceChart } from '@/lib/queries';
import type { PositionHistoryRow, PositionPriceChartData, PositionPriceChartEvent } from '@/lib/types';
import { EVENT_COLORS, useChartColors, withAlpha } from '@/lib/chart-colors';

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

type ScatterRow = Row & {
  event: PositionPriceChartEvent['event'];
  markPrice: number | null;
  weight_pct: number | null;
  prev_weight_pct: number | null;
  weight_change_pct: number | null;
  reason: string | null;
};

function ChartTooltip({
  active,
  payload,
  weightByDate,
}: {
  active?: boolean;
  payload?: Array<{ payload: Row & Partial<ScatterRow> }>;
  /** Last known portfolio weight % for each trading day (forward-filled from position_history). */
  weightByDate?: Map<string, number>;
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload as ScatterRow;
  if ('event' in p && p.event) {
    return (
      <div className="rounded-lg border border-hair bg-term-bg px-3 py-2 text-[0.82rem] shadow-lg max-w-xs">
        <p className="font-mono font-semibold" style={{ color: eventDotColor(p.event) }}>
          {p.event}
        </p>
        <p className="text-ink-soft mt-1 font-mono">{p.date}</p>
        <p className="text-ink-soft tabular-nums mt-0.5">
          Price:{' '}
          {p.markPrice != null ? `$${p.markPrice.toFixed(2)}` : p.close != null ? `$${p.close.toFixed(2)}` : '—'}
        </p>
        {p.weight_pct != null ? (
          <p className="text-ink-mute mt-1 tabular-nums">Weight after: {p.weight_pct.toFixed(2)}%</p>
        ) : null}
        {p.weight_change_pct != null ? (
          <p className="text-ink-mute tabular-nums">
            Δ weight: {p.weight_change_pct > 0 ? '+' : ''}
            {p.weight_change_pct.toFixed(2)}pp
          </p>
        ) : null}
        {p.reason ? <p className="text-ink-mute mt-1.5 text-[11px] leading-snug">{p.reason}</p> : null}
      </div>
    );
  }
  const w = weightByDate?.get(p.date);
  return (
    <div className="rounded-lg border border-hair bg-term-bg px-3 py-2 text-[0.82rem] shadow-lg">
      <p className="font-mono text-ink-soft">{p.date}</p>
      <p className="text-ink tabular-nums mt-0.5">${Number(p.close).toFixed(2)}</p>
      {typeof w === 'number' ? (
        <p className="text-ink-mute tabular-nums mt-1 text-[11px]">Weight (portfolio): {w.toFixed(2)}%</p>
      ) : null}
    </div>
  );
}

function PriceChartBrushPanel({
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
  const chart = useChartColors();
  const containerRef = useRef<HTMLDivElement>(null);
  const gradientId = useId().replace(/:/g, '');
  const { brushStart, brushEnd, setBrushStart, setBrushEnd } = useBrushRange(chartRows.length);

  const visibleRows = useMemo(() => {
    if (!chartRows.length) return [];
    const end = Math.min(brushEnd, chartRows.length - 1);
    const start = Math.max(0, Math.min(brushStart, end));
    return chartRows.slice(start, end + 1);
  }, [chartRows, brushStart, brushEnd]);

  const markers = useMemo(() => {
    const evs = events.filter((e) => e.event !== 'HOLD');
    if (!chartRows.length) return [] as ScatterRow[];
    const first = chartRows[0].date;
    const last = chartRows[chartRows.length - 1].date;
    const inRange = evs.filter((e) => e.date >= first && e.date <= last);
    return inRange
      .map((ev) => {
        const tr = rowOnOrAfter(chartRows, ev.date);
        if (!tr) return null;
        const row: ScatterRow = {
          date: tr.date,
          close: tr.close,
          is_trading_day: tr.is_trading_day,
          event: ev.event,
          markPrice: ev.price,
          weight_pct: ev.weight_pct,
          prev_weight_pct: ev.prev_weight_pct,
          weight_change_pct: ev.weight_change_pct,
          reason: ev.reason,
        };
        return row;
      })
      .filter((x): x is ScatterRow => x != null);
  }, [events, chartRows]);

  const scatterInView = useMemo(() => {
    if (!visibleRows.length || !markers.length) return [] as ScatterRow[];
    const d0 = visibleRows[0].date;
    const d1 = visibleRows[visibleRows.length - 1].date;
    return markers.filter((m) => m.date >= d0 && m.date <= d1);
  }, [visibleRows, markers]);

  const onBrushChange = useCallback((e: { startIndex?: number; endIndex?: number }) => {
    if (e.startIndex !== undefined) setBrushStart(e.startIndex);
    if (e.endIndex !== undefined) setBrushEnd(e.endIndex);
  }, [setBrushEnd, setBrushStart]);

  const resetView = useCallback(() => {
    if (!chartRows.length) return;
    setBrushStart(0);
    setBrushEnd(chartRows.length - 1);
  }, [chartRows, setBrushEnd, setBrushStart]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !chartRows.length) return;

    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) return;
      const n = chartRows.length;
      if (n < 2) return;
      let start = Math.max(0, Math.min(brushStart, brushEnd));
      let end = Math.max(start, Math.min(n - 1, Math.max(brushStart, brushEnd)));
      const span = end - start + 1;
      const mid = (start + end) / 2;

      e.preventDefault();

      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        const step = Math.max(1, Math.floor(span * 0.12));
        const dir = e.deltaX > 0 ? 1 : -1;
        let ns = start + dir * step;
        let ne = ns + span - 1;
        if (ns < 0) {
          ne -= ns;
          ns = 0;
        }
        if (ne > n - 1) {
          ns -= ne - (n - 1);
          ne = n - 1;
        }
        if (ns < 0) ns = 0;
        setBrushStart(ns);
        setBrushEnd(ne);
        return;
      }

      const zoomIn = e.deltaY < 0;
      let newSpan = zoomIn ? Math.max(5, Math.floor(span * 0.88)) : Math.min(n, Math.ceil(span * 1.12));
      newSpan = Math.max(3, Math.min(n, newSpan));
      let newStart = Math.round(mid - newSpan / 2);
      let newEnd = newStart + newSpan - 1;
      if (newStart < 0) {
        newEnd -= newStart;
        newStart = 0;
      }
      if (newEnd > n - 1) {
        newStart -= newEnd - (n - 1);
        newEnd = n - 1;
      }
      if (newStart < 0) newStart = 0;
      setBrushStart(newStart);
      setBrushEnd(newEnd);
    };

    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [brushEnd, brushStart, chartRows, setBrushEnd, setBrushStart]);

  const entryLineDate = useMemo(() => {
    if (!firstEntryDate || !visibleRows.length) return null;
    const a = visibleRows[0].date;
    const b = visibleRows[visibleRows.length - 1].date;
    if (firstEntryDate < a || firstEntryDate > b) return null;
    return rowOnOrAfter(visibleRows, firstEntryDate)?.date ?? null;
  }, [firstEntryDate, visibleRows]);

  const chartEnd = chartRows[chartRows.length - 1].date;

  return (
    <div ref={containerRef} className="rounded-xl border border-hair bg-term-bg/20 overflow-hidden">
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
            onClick={resetView}
            className="text-[11px] px-2.5 py-1 rounded-lg border border-hair text-ink-soft hover:bg-ink/[0.04] hover:text-ink transition-colors"
          >
            Fit all
          </button>
        </div>
      </div>

      <div className="h-[min(320px,42vh)] min-h-[220px] w-full px-2 pb-1">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={visibleRows} margin={{ top: 12, right: 14, left: 4, bottom: 4 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={chart.accent} stopOpacity={0.35} />
                <stop offset="100%" stopColor={chart.accent} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={chart.hair} vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: chart.axis, fontSize: 11 }}
              tickFormatter={(d: string) => (d?.length >= 10 ? d.slice(5) : d)}
              minTickGap={32}
            />
            <YAxis
              domain={['auto', 'auto']}
              tick={{ fill: chart.axis, fontSize: 11 }}
              width={52}
              tickFormatter={(v) => (typeof v === 'number' ? v.toFixed(0) : String(v))}
            />
            <Tooltip
              content={(tipProps) => (
                <ChartTooltip
                  active={tipProps.active}
                  payload={tipProps.payload as Array<{ payload: Row & Partial<ScatterRow> }> | undefined}
                  weightByDate={weightByDate}
                />
              )}
              cursor={{ stroke: withAlpha(chart.ink, 0.12) }}
            />
            {entryLineDate ? (
              <ReferenceLine
                x={entryLineDate}
                stroke={withAlpha(chart.up, 0.45)}
                strokeDasharray="4 4"
                label={{ value: 'Entry', fill: chart.axis, fontSize: 10 }}
              />
            ) : null}
            <Area
              type="monotone"
              dataKey="close"
              stroke="none"
              fill={`url(#${gradientId})`}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="close"
              stroke={chart.accent}
              dot={false}
              strokeWidth={2}
              name="Close"
              isAnimationActive={false}
            />
            <Scatter
              data={scatterInView}
              dataKey="close"
              fill={chart.accent}
              isAnimationActive={false}
              shape={(raw: unknown) => {
                const props = raw as { cx?: number; cy?: number; payload?: ScatterRow };
                const { cx, cy, payload } = props;
                if (cx == null || cy == null || !payload?.event) return <g />;
                const r = payload.event === 'TRIM' || payload.event === 'ADD' ? 4 : 5;
                return (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={r}
                    fill={eventDotColor(payload.event)}
                    stroke={chart.bg}
                    strokeWidth={1.5}
                  />
                );
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="h-16 px-2 pb-3">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartRows} margin={{ top: 2, right: 14, left: 4, bottom: 2 }}>
            <XAxis dataKey="date" hide />
            <YAxis hide domain={['auto', 'auto']} />
            <Line type="monotone" dataKey="close" stroke={chart.accent} strokeOpacity={0.4} dot={false} strokeWidth={1} isAnimationActive={false} />
            <Brush
              dataKey="date"
              height={28}
              stroke={chart.accent}
              fill={withAlpha(chart.accent, 0.08)}
              travellerWidth={10}
              startIndex={brushStart}
              endIndex={brushEnd}
              onChange={onBrushChange}
              tickFormatter={(d: string) => (typeof d === 'string' && d.length >= 7 ? d.slice(5) : '')}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
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
    <PriceChartBrushPanel
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
