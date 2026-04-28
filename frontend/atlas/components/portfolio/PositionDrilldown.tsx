'use client';

import { useCallback, useEffect, useId, useMemo, useState } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
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
  type DrilldownChartRow,
  type DrilldownWindow,
} from '@/lib/position-drilldown';
import type { DashboardPositionEvent, Position, PositionHistoryRow, Thesis } from '@/lib/types';
import { formatAllocationCategory } from '@/components/portfolio/tabs/palette-and-format';
import { pnlColor } from '@/components/ui';

function thesisNames(ids: string[], thesisById: Map<string, Thesis>): string {
  if (!ids.length) return '—';
  return ids.map((id) => thesisById.get(id)?.name ?? id).join(', ');
}

function eventMarkerColor(ev: DashboardPositionEvent['event']): string {
  if (ev === 'OPEN') return '#22c55e';
  if (ev === 'EXIT') return '#ef4444';
  if (ev === 'ADD') return '#38bdf8';
  if (ev === 'TRIM') return '#f59e0b';
  return '#71717a';
}

function eventLabelClass(ev: DashboardPositionEvent['event']): string {
  if (ev === 'OPEN') return 'text-fin-green';
  if (ev === 'EXIT') return 'text-fin-red';
  if (ev === 'ADD') return 'text-fin-blue';
  if (ev === 'TRIM') return 'text-fin-amber';
  return 'text-text-muted';
}

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
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
  const gradientId = useId().replace(/:/g, '');
  const contribId = useId().replace(/:/g, '');

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

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [chartRows, setChartRows] = useState<DrilldownChartRow[]>([]);
  const [priceSorted, setPriceSorted] = useState<Array<{ date: string; close: number }>>([]);

  useEffect(() => {
    let cancelled = false;
    /* eslint-disable react-hooks/set-state-in-effect -- fetch lifecycle for expanded row */
    setLoading(true);
    setErr(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    fetchPositionPriceChart(position.ticker, fetchFrom, rangeEnd)
      .then((d) => {
        if (cancelled) return;
        const sorted = [...(d.priceHistory ?? [])].sort((a, b) => a.date.localeCompare(b.date));
        setPriceSorted(sorted);
        const evAsc = filterActivityEventsAscending(positionEvents, position.ticker, displayStart, rangeEnd);
        const rows = buildDrilldownChartRows(sorted, positionHistory, position.ticker, displayStart, rangeEnd, evAsc);
        setChartRows(rows);
      })
      .catch((e) => {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : 'Failed to load');
          setChartRows([]);
          setPriceSorted([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [position.ticker, fetchFrom, rangeEnd, displayStart, positionHistory, positionEvents]);

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

  const windowButtons = (['1m', '3m', 'ytd', '1y', 'itd'] as const).map((k) => (
    <button
      key={k}
      type="button"
      onClick={() => setUserWindow(k)}
      className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
        windowPreset === k
          ? 'bg-fin-blue/20 text-fin-blue border border-fin-blue/40'
          : 'border border-border-subtle text-text-muted hover:bg-white/[0.04]'
      }`}
    >
      {DRILLDOWN_WINDOW_LABELS[k]}
    </button>
  ));

  return (
    <div className="rounded-lg border border-border-subtle bg-bg-secondary/40 p-4 md:p-5 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-semibold truncate">
            {position.ticker}
            {position.name ? <span className="text-text-muted font-normal"> — {position.name}</span> : null}
          </p>
          <p className="text-xs text-text-muted">
            As of {rangeEnd}
            {mode === 'performance' && performanceRange ? ` · Range ${performanceRange.start} → ${rangeEnd}` : null}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">{windowButtons}</div>
      </div>

      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 lg:grid-cols-6">
        <div className="rounded-md border border-border-subtle bg-bg-primary/40 p-3">
          <p className="text-[11px] font-semibold text-text-muted tracking-wide">Weight</p>
          <p className="text-sm mt-1 font-mono tabular-nums">
            {position.weight_actual != null ? `${position.weight_actual.toFixed(1)}%` : '—'}
          </p>
        </div>
        <div className="rounded-md border border-border-subtle bg-bg-primary/40 p-3">
          <p className="text-[11px] font-semibold text-text-muted tracking-wide">Avg entry</p>
          <p className="text-sm mt-1 font-mono tabular-nums">
            {avgEntry != null ? `$${avgEntry.toFixed(2)}` : '—'}
          </p>
        </div>
        <div className="rounded-md border border-border-subtle bg-bg-primary/40 p-3">
          <p className="text-[11px] font-semibold text-text-muted tracking-wide">Unrealized</p>
          <p className={`text-sm mt-1 font-mono tabular-nums font-semibold ${pnlColor(pnlVsAvg)}`}>
            {pnlVsAvg != null ? `${pnlVsAvg >= 0 ? '+' : ''}${pnlVsAvg.toFixed(2)}%` : '—'}
          </p>
        </div>
        <div className="rounded-md border border-border-subtle bg-bg-primary/40 p-3">
          <p className="text-[11px] font-semibold text-text-muted tracking-wide">Δ weight (window)</p>
          <p className={`text-sm mt-1 font-mono tabular-nums ${pnlColor(netW)}`}>
            {netW != null ? `${netW >= 0 ? '+' : ''}${netW.toFixed(2)}pp` : '—'}
          </p>
        </div>
        <div className="rounded-md border border-border-subtle bg-bg-primary/40 p-3 col-span-2 lg:col-span-2">
          <p className="text-[11px] font-semibold text-text-muted tracking-wide">Category / thesis</p>
          <p className="text-sm mt-1 truncate">
            {formatAllocationCategory(position.category)} · {thesisNames(position.thesis_ids, thesisById)}
          </p>
        </div>
      </div>

      {mode === 'performance' && periodContribPpt != null && !Number.isNaN(periodContribPpt) ? (
        <div className="rounded-md border border-border-subtle bg-bg-primary/30 px-3 py-2 text-sm">
          <span className="text-text-muted">Attributed contribution (window): </span>
          <span className={`font-mono tabular-nums font-semibold ${pnlColor(periodContribPpt)}`}>
            {periodContribPpt >= 0 ? '+' : ''}
            {periodContribPpt.toFixed(3)} ppt
          </span>
          <span className="text-text-muted text-xs ml-2">(daily return × prior-day weight)</span>
        </div>
      ) : null}

      {loading ? (
        <p className="text-sm text-text-muted py-6 text-center">Loading chart data…</p>
      ) : err ? (
        <p className="text-sm text-fin-red py-4">{err}</p>
      ) : chartRows.length >= 2 ? (
        <div className="space-y-2">
          <p className="text-[11px] font-semibold text-text-muted tracking-wide">Weight &amp; price</p>
          <div className="h-[280px] w-full min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartRows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="rgb(59,130,246)" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="rgb(59,130,246)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#71717a" minTickGap={24} />
                <YAxis
                  yAxisId="w"
                  tick={{ fontSize: 10 }}
                  stroke="#71717a"
                  domain={[0, 'auto']}
                  tickFormatter={(v) => `${v}%`}
                  width={44}
                />
                <YAxis
                  yAxisId="p"
                  orientation="right"
                  tick={{ fontSize: 10 }}
                  stroke="#71717a"
                  domain={['auto', 'auto']}
                  tickFormatter={(v) => `$${v}`}
                  width={56}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const row = payload[0].payload as DrilldownChartRow;
                    return (
                      <div className="rounded-lg border border-border-subtle bg-bg-primary px-3 py-2 text-[0.82rem] shadow-lg max-w-sm">
                        <p className="font-mono text-text-secondary text-xs">{row.date}</p>
                        <p className="text-text-primary tabular-nums mt-1">Close ${row.close.toFixed(2)}</p>
                        <p className="text-text-muted tabular-nums text-xs mt-0.5">Weight {row.weightPct.toFixed(2)}%</p>
                        {row.dayEvents.length > 0 ? (
                          <ul className="mt-2 space-y-1 text-xs">
                            {row.dayEvents.map((ev, i) => (
                              <li key={i} className={eventLabelClass(ev.event)}>
                                {ev.event}
                                {ev.weight_change_pct != null
                                  ? ` · Δ ${ev.weight_change_pct >= 0 ? '+' : ''}${ev.weight_change_pct.toFixed(2)}pp`
                                  : null}
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    );
                  }}
                />
                <Area
                  yAxisId="w"
                  type="monotone"
                  dataKey="weightPct"
                  stroke="rgb(59,130,246)"
                  strokeWidth={1.5}
                  fill={`url(#${gradientId})`}
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="p"
                  type="monotone"
                  dataKey="close"
                  stroke="#a78bfa"
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
                {markerPoints.map((m) => (
                  <ReferenceDot
                    key={m.date}
                    x={m.date}
                    y={m.close}
                    yAxisId="p"
                    r={5}
                    fill={eventMarkerColor(m.event)}
                    stroke="rgba(0,0,0,0.35)"
                    strokeWidth={1}
                    isFront
                  />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <p className="text-sm text-text-muted py-2">
          Not enough price history in this window for the chart. See activity below.
        </p>
      )}

      {mode === 'performance' && contributionSeries.length >= 2 ? (
        <div className="space-y-2">
          <p className="text-[11px] font-semibold text-text-muted tracking-wide">Cumulative contribution (ppt)</p>
          <div className="h-[160px] w-full min-w-0">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={contributionSeries} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id={contribId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="rgb(34,197,94)" stopOpacity={0.2} />
                    <stop offset="100%" stopColor="rgb(34,197,94)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#71717a" minTickGap={24} />
                <YAxis tick={{ fontSize: 10 }} stroke="#71717a" width={48} />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const cum = payload.find((p) => p.dataKey === 'cumPp')?.value;
                    const daily = payload.find((p) => p.dataKey === 'dailyPp')?.value;
                    return (
                      <div className="rounded-lg border border-border-subtle bg-bg-primary px-3 py-2 text-[0.82rem] shadow-lg">
                        <p className="font-mono text-text-secondary text-xs">{String(label)}</p>
                        <p className="text-text-primary tabular-nums mt-1">
                          Cumulative:{' '}
                          {typeof cum === 'number' ? `${cum >= 0 ? '+' : ''}${cum.toFixed(4)} ppt` : '—'}
                        </p>
                        <p className="text-text-muted tabular-nums text-xs mt-0.5">
                          Daily:{' '}
                          {typeof daily === 'number' ? `${daily >= 0 ? '+' : ''}${daily.toFixed(4)} ppt` : '—'}
                        </p>
                      </div>
                    );
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="dailyPp"
                  stroke="transparent"
                  dot={false}
                  strokeWidth={0}
                  isAnimationActive={false}
                  name="Daily ppt"
                />
                <Area
                  type="monotone"
                  dataKey="cumPp"
                  stroke="#22c55e"
                  strokeWidth={1.5}
                  fill={`url(#${contribId})`}
                  isAnimationActive={false}
                  name="Cumulative ppt"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : null}

      <div className="space-y-2">
        <p className="text-[11px] font-semibold text-text-muted tracking-wide">Activity</p>
        <div className="overflow-x-auto rounded-md border border-border-subtle">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="text-left text-text-muted text-xs uppercase tracking-wider border-b border-border-subtle bg-bg-primary/30">
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Action</th>
                <th className="px-3 py-2 text-right">Δ weight</th>
                <th className="px-3 py-2 text-right">Before → after</th>
                <th className="px-3 py-2 text-right">Price</th>
                <th className="px-3 py-2">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {ledgerDesc.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-text-muted text-sm">
                    No OPEN / ADD / TRIM / EXIT events in this window.
                  </td>
                </tr>
              ) : (
                ledgerDesc.map((e, i) => {
                  const ledgerPx = onLedgerPrice(e);
                  return (
                  <tr key={`${e.date}-${e.event}-${i}`} className="hover:bg-white/[0.02]">
                    <td className="px-3 py-2 font-mono text-xs text-text-secondary whitespace-nowrap">{e.date}</td>
                    <td className="px-3 py-2">
                      <span className={`font-semibold text-xs ${eventLabelClass(e.event)}`}>{e.event}</span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-xs">
                      {e.weight_change_pct != null
                        ? `${e.weight_change_pct >= 0 ? '+' : ''}${e.weight_change_pct.toFixed(2)}pp`
                        : '—'}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-xs text-text-secondary">
                      {e.prev_weight_pct != null && e.weight_pct != null
                        ? `${e.prev_weight_pct.toFixed(2)} → ${e.weight_pct.toFixed(2)}%`
                        : '—'}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-xs">
                      {ledgerPx != null ? `$${ledgerPx.toFixed(2)}` : '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-text-muted max-w-[280px]">{e.reason ?? '—'}</td>
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
