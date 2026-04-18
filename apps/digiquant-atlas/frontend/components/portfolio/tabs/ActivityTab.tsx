'use client';

import { useCallback, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, GripVertical } from 'lucide-react';
import { Badge } from '@/components/ui';
import { ActivityTickerMultiSelect } from '@/components/portfolio/activity-ticker-multi-select';
import type { DashboardPositionEvent, Thesis } from '@/lib/types';

const EVENT_TYPES = ['OPEN', 'EXIT', 'TRIM', 'ADD', 'HOLD'] as const;
type LedgerEventType = (typeof EVENT_TYPES)[number];

type ColumnId =
  | 'date'
  | 'ticker'
  | 'event'
  | 'prev_weight'
  | 'weight'
  | 'delta'
  | 'reason'
  | 'price';

const ALL_COLUMNS: ColumnId[] = [
  'date',
  'ticker',
  'event',
  'prev_weight',
  'weight',
  'delta',
  'reason',
  'price',
];

const COLUMN_LABEL: Record<ColumnId, string> = {
  date: 'Date',
  ticker: 'Ticker',
  event: 'Event',
  prev_weight: 'Prior wt',
  weight: 'Weight',
  delta: 'Δ wt',
  reason: 'Reason',
  price: 'Price',
};

const DEFAULT_VISIBLE: Record<ColumnId, boolean> = {
  date: true,
  ticker: true,
  event: true,
  prev_weight: true,
  weight: true,
  delta: true,
  reason: true,
  price: false,
};

function eventBadgeVariant(
  ev: DashboardPositionEvent['event']
): 'green' | 'red' | 'amber' | 'default' {
  if (ev === 'OPEN') return 'green';
  if (ev === 'EXIT') return 'red';
  if (ev === 'ADD') return 'green';
  if (ev === 'TRIM') return 'amber';
  return 'default';
}

/** ISO date YYYY-MM-DD + calendar days (UTC-safe for portfolio dates). */
function addCalendarDays(iso: string, deltaDays: number): string {
  const [y, m, d] = iso.split('-').map(Number);
  if (!y || !m || !d) return iso;
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + deltaDays);
  return dt.toISOString().slice(0, 10);
}

type RangePreset = '7d' | '30d' | 'all';

type SortDir = 'asc' | 'desc';

function cmpStr(a: string, b: string): number {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

/** Numeric compare; nulls sort last in ascending order. */
function cmpNumNullLast(a: number | null, b: number | null): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

function sortEvents(
  rows: DashboardPositionEvent[],
  sortKey: ColumnId,
  sortDir: SortDir
): DashboardPositionEvent[] {
  const mul = sortDir === 'asc' ? 1 : -1;
  const out = [...rows];
  out.sort((a, b) => {
    let c = 0;
    switch (sortKey) {
      case 'date':
        c = cmpStr(a.date, b.date);
        break;
      case 'ticker':
        c = cmpStr(a.ticker, b.ticker);
        break;
      case 'event':
        c = cmpStr(a.event, b.event);
        break;
      case 'prev_weight':
        c = cmpNumNullLast(a.prev_weight_pct, b.prev_weight_pct);
        break;
      case 'weight':
        c = cmpNumNullLast(a.weight_pct, b.weight_pct);
        break;
      case 'delta':
        c = cmpNumNullLast(a.weight_change_pct, b.weight_change_pct);
        break;
      case 'reason':
        c = cmpStr((a.reason ?? '').toLowerCase(), (b.reason ?? '').toLowerCase());
        break;
      case 'price':
        c = cmpNumNullLast(a.price, b.price);
        break;
      default:
        c = 0;
    }
    if (c !== 0) return mul * c;
    const byDate = cmpStr(a.date, b.date);
    if (byDate !== 0) return -byDate;
    return cmpStr(a.ticker, b.ticker);
  });
  return out;
}

function SortGlyph({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ArrowUpDown className="inline size-3.5 opacity-40" aria-hidden />;
  return dir === 'asc' ? (
    <ArrowUp className="inline size-3.5 text-fin-blue" aria-hidden />
  ) : (
    <ArrowDown className="inline size-3.5 text-fin-blue" aria-hidden />
  );
}

export default function ActivityTab(props: {
  activityEvents: DashboardPositionEvent[];
  thesisById: Map<string, Thesis>;
  /** Latest portfolio snapshot date — used for “New” badges on that digest date. */
  lastRunDate: string | null;
}) {
  const { activityEvents, thesisById, lastRunDate } = props;
  const [preset, setPreset] = useState<RangePreset>('all');

  const [selectedTickers, setSelectedTickers] = useState<string[]>([]);
  const [eventMask, setEventMask] = useState<Record<LedgerEventType, boolean>>(() => ({
    OPEN: true,
    EXIT: true,
    TRIM: true,
    ADD: true,
    HOLD: true,
  }));

  const [sort, setSort] = useState<{ key: ColumnId; dir: SortDir }>({ key: 'date', dir: 'desc' });

  const [columnOrder, setColumnOrder] = useState<ColumnId[]>(() => [...ALL_COLUMNS]);
  const [visible, setVisible] = useState<Record<ColumnId, boolean>>(() => ({ ...DEFAULT_VISIBLE }));

  const latestLedgerDate = useMemo(() => {
    if (!activityEvents.length) return null;
    return activityEvents.reduce((best, ev) => (ev.date > best ? ev.date : best), activityEvents[0].date);
  }, [activityEvents]);

  const rangeAnchorDate = latestLedgerDate ?? lastRunDate ?? null;

  const eventFilterActive = useMemo(
    () => EVENT_TYPES.some((t) => !eventMask[t]),
    [eventMask]
  );

  const rangeFiltered = useMemo(() => {
    if (preset === 'all' || !rangeAnchorDate) return activityEvents;
    const days = preset === '7d' ? 7 : 30;
    const cutoff = addCalendarDays(rangeAnchorDate, -days);
    return activityEvents.filter((ev) => ev.date >= cutoff);
  }, [activityEvents, preset, rangeAnchorDate]);

  const tickerUniverse = useMemo(() => {
    const set = new Set<string>();
    for (const ev of activityEvents) set.add(ev.ticker.toUpperCase());
    return [...set].sort((a, b) => a.localeCompare(b));
  }, [activityEvents]);

  const fieldFiltered = useMemo(() => {
    return rangeFiltered.filter((ev) => {
      if (eventFilterActive && !eventMask[ev.event as LedgerEventType]) return false;
      if (selectedTickers.length > 0 && !selectedTickers.includes(ev.ticker.toUpperCase())) return false;
      return true;
    });
  }, [rangeFiltered, selectedTickers, eventMask, eventFilterActive]);

  const addTicker = useCallback((t: string) => {
    const u = t.toUpperCase();
    setSelectedTickers((prev) => (prev.includes(u) ? prev : [...prev, u].sort((a, b) => a.localeCompare(b))));
  }, []);

  const removeTicker = useCallback((t: string) => {
    setSelectedTickers((prev) => prev.filter((x) => x !== t));
  }, []);

  const sortedEvents = useMemo(
    () => sortEvents(fieldFiltered, sort.key, sort.dir),
    [fieldFiltered, sort]
  );

  const orderedVisibleColumns = useMemo(
    () => columnOrder.filter((c) => visible[c]),
    [columnOrder, visible]
  );

  const rangeSummary = useMemo(() => {
    if (preset === 'all')
      return `${sortedEvents.length} event${sortedEvents.length !== 1 ? 's' : ''}`;
    if (!rangeAnchorDate) return `${sortedEvents.length} shown`;
    const days = preset === '7d' ? 7 : 30;
    return `${sortedEvents.length} in ${days}d`;
  }, [preset, sortedEvents.length, rangeAnchorDate]);

  const toggleSort = useCallback((key: ColumnId) => {
    setSort((s) =>
      s.key === key
        ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: key === 'date' ? 'desc' : 'asc' }
    );
  }, []);

  const onDragStart = useCallback((e: React.DragEvent, id: ColumnId) => {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', id);
  }, []);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback((e: React.DragEvent, targetId: ColumnId) => {
    e.preventDefault();
    const raw = e.dataTransfer.getData('text/plain') as ColumnId;
    const src = ALL_COLUMNS.includes(raw) ? raw : null;
    if (!src || src === targetId) return;
    setColumnOrder((prev) => {
      const next = prev.filter((x) => x !== src);
      const idx = next.indexOf(targetId);
      if (idx < 0) return prev;
      next.splice(idx, 0, src);
      return next;
    });
  }, []);

  const resetFilters = useCallback(() => {
    setSelectedTickers([]);
    setEventMask({ OPEN: true, EXIT: true, TRIM: true, ADD: true, HOLD: true });
  }, []);

  const toggleEventType = useCallback((t: LedgerEventType) => {
    setEventMask((m) => {
      const next = { ...m, [t]: !m[t] };
      if (!EVENT_TYPES.some((x) => next[x])) return m;
      return next;
    });
  }, []);

  const toggleColumn = useCallback((c: ColumnId) => {
    if (c === 'date') return;
    setVisible((v) => ({ ...v, [c]: !v[c] }));
  }, []);

  function cellWrapperClass(col: ColumnId): string {
    switch (col) {
      case 'prev_weight':
        return 'hidden md:table-cell';
      case 'delta':
        return 'hidden sm:table-cell';
      case 'price':
        return 'hidden lg:table-cell';
      default:
        return '';
    }
  }

  const renderCell = (col: ColumnId, ev: DashboardPositionEvent, i: number) => {
    const isNewDay = Boolean(lastRunDate && ev.date === lastRunDate);

    switch (col) {
      case 'date':
        return (
          <td
            key={`${col}-${i}`}
            className={`${cellWrapperClass(col)} px-3 py-3 font-mono text-xs text-text-secondary md:px-5`}
          >
            <span className="inline-flex items-center gap-2">
              {ev.date}
              {isNewDay ? (
                <span className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide bg-fin-amber/20 text-fin-amber border border-fin-amber/30">
                  New
                </span>
              ) : null}
            </span>
          </td>
        );
      case 'ticker':
        return (
          <td key={`${col}-${i}`} className={`${cellWrapperClass(col)} px-3 py-3 font-semibold md:px-5`}>
            {ev.ticker}
          </td>
        );
      case 'event':
        return (
          <td key={`${col}-${i}`} className={`${cellWrapperClass(col)} px-3 py-3 md:px-5`}>
            <Badge variant={eventBadgeVariant(ev.event)}>{ev.event}</Badge>
          </td>
        );
      case 'prev_weight':
        return (
          <td
            key={`${col}-${i}`}
            className={`${cellWrapperClass(col)} px-5 py-3 text-right font-mono tabular-nums text-xs text-text-secondary`}
            title={ev.prev_weight_pct != null ? `Previous weight: ${ev.prev_weight_pct.toFixed(2)}%` : undefined}
          >
            {ev.prev_weight_pct != null ? `${ev.prev_weight_pct.toFixed(2)}%` : '—'}
          </td>
        );
      case 'weight':
        return (
          <td
            key={`${col}-${i}`}
            className={`${cellWrapperClass(col)} px-3 py-3 text-right font-mono tabular-nums text-xs md:px-5`}
            title="Weight after this event"
          >
            {ev.weight_pct != null ? `${ev.weight_pct.toFixed(2)}%` : '—'}
          </td>
        );
      case 'delta':
        return (
          <td
            key={`${col}-${i}`}
            className={`${cellWrapperClass(col)} px-5 py-3 text-right font-mono tabular-nums text-xs text-text-secondary`}
          >
            {ev.weight_change_pct != null
              ? `${ev.weight_change_pct > 0 ? '+' : ''}${ev.weight_change_pct.toFixed(2)}pp`
              : '—'}
          </td>
        );
      case 'reason':
        return (
          <td
            key={`${col}-${i}`}
            className={`${cellWrapperClass(col)} max-w-[min(28rem,40vw)] truncate px-3 py-3 text-xs text-text-muted md:px-5 lg:max-w-md`}
            title={ev.reason ?? undefined}
          >
            {ev.reason ?? '—'}
          </td>
        );
      case 'price':
        return (
          <td
            key={`${col}-${i}`}
            className={`${cellWrapperClass(col)} px-5 py-3 text-right font-mono tabular-nums text-xs text-text-secondary`}
          >
            {ev.price != null ? `$${Number(ev.price).toFixed(2)}` : '—'}
          </td>
        );
      default:
        return null;
    }
  };

  const colSpan = Math.max(orderedVisibleColumns.length, 1);

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="border-b border-border-subtle bg-bg-secondary px-4 py-4 md:px-6 md:py-5">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
          <h3 className="text-lg font-semibold">Activity</h3>
          <p className="text-[11px] text-text-muted font-mono">{rangeSummary}</p>
        </div>

        <div className="mt-4 flex flex-col gap-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
            <span className="shrink-0 text-[10px] uppercase tracking-wider text-text-muted sm:w-24">
              Time window
            </span>
            <div className="flex flex-wrap gap-2">
              {(['7d', '30d', 'all'] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setPreset(k)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium border transition-colors ${
                    preset === k
                      ? 'border-fin-blue/40 bg-fin-blue/15 text-fin-blue'
                      : 'border-border-subtle text-text-muted hover:text-text-primary hover:bg-white/[0.04]'
                  }`}
                >
                  {k === '7d' ? '7 days' : k === '30d' ? '30 days' : 'All'}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:gap-4">
            <span className="shrink-0 pt-0.5 text-[10px] uppercase tracking-wider text-text-muted sm:w-24">
              Events
            </span>
            <div className="flex min-w-0 flex-1 flex-wrap gap-2">
              {EVENT_TYPES.map((t) => (
                <label
                  key={t}
                  className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border-subtle bg-bg-primary px-2 py-1 text-[11px] text-text-secondary hover:bg-white/[0.03]"
                >
                  <input
                    type="checkbox"
                    className="accent-fin-blue"
                    checked={eventMask[t]}
                    onChange={() => toggleEventType(t)}
                  />
                  {t}
                </label>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:gap-4">
            <span className="shrink-0 text-[10px] uppercase tracking-wider text-text-muted sm:w-24">Symbols</span>
            <div className="min-w-0 flex-1">
              <ActivityTickerMultiSelect
                universe={tickerUniverse}
                selected={selectedTickers}
                onAdd={addTicker}
                onRemove={removeTicker}
              />
            </div>
          </div>

          <div className="flex flex-wrap justify-end gap-2 border-t border-border-subtle pt-3">
            <button
              type="button"
              onClick={resetFilters}
              className="rounded-md border border-border-subtle px-2.5 py-1.5 text-xs text-text-muted hover:text-text-primary hover:bg-white/[0.04]"
            >
              Reset filters
            </button>
            <details className="group relative">
              <summary className="list-none cursor-pointer rounded-md border border-border-subtle px-2.5 py-1.5 text-xs text-text-muted hover:text-text-primary hover:bg-white/[0.04] [&::-webkit-details-marker]:hidden">
                Columns
              </summary>
              <div className="absolute right-0 z-20 mt-1 min-w-[11rem] rounded-md border border-border-subtle bg-bg-secondary p-2 shadow-lg">
                <p className="mb-2 text-[10px] uppercase tracking-wider text-text-muted">Visible fields</p>
                <ul className="space-y-1.5">
                  {ALL_COLUMNS.map((c) => (
                    <li key={c}>
                      <label
                        className={`flex items-center gap-2 text-xs ${
                          c === 'date' ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
                        }`}
                      >
                        <input
                          type="checkbox"
                          className="accent-fin-blue"
                          checked={visible[c]}
                          disabled={c === 'date'}
                          onChange={() => toggleColumn(c)}
                        />
                        {COLUMN_LABEL[c]}
                      </label>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 border-t border-border-subtle pt-2 text-[10px] text-text-muted leading-snug">
                  Drag <GripVertical className="inline size-3 align-text-bottom opacity-60" /> on a header to reorder columns.
                </p>
              </div>
            </details>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-0 text-sm md:min-w-[720px]">
          <thead>
            <tr className="text-text-muted text-xs uppercase tracking-wider">
              {orderedVisibleColumns.map((col) => (
                <th
                  key={col}
                  className={`px-3 py-3 text-left md:px-5 ${cellWrapperClass(col)} ${
                    col === 'prev_weight' || col === 'weight' || col === 'delta' || col === 'price'
                      ? 'text-right'
                      : ''
                  }`}
                  onDragOver={onDragOver}
                  onDrop={(e) => onDrop(e, col)}
                >
                  <div
                    className={`flex items-center gap-1 ${
                      col === 'prev_weight' || col === 'weight' || col === 'delta' || col === 'price'
                        ? 'justify-end'
                        : ''
                    }`}
                  >
                    <span
                      draggable
                      onDragStart={(e) => onDragStart(e, col)}
                      className="cursor-grab touch-none text-text-muted hover:text-text-secondary active:cursor-grabbing"
                      title="Drag to reorder column"
                      aria-hidden
                    >
                      <GripVertical className="size-3.5 shrink-0 opacity-50" />
                    </span>
                    <button
                      type="button"
                      onClick={() => toggleSort(col)}
                      className={`inline-flex items-center gap-1 rounded px-0.5 py-0.5 text-left hover:text-text-primary ${
                        col === 'prev_weight' || col === 'weight' || col === 'delta' || col === 'price'
                          ? 'ml-auto'
                          : ''
                      }`}
                      aria-label={`Sort by ${COLUMN_LABEL[col]}`}
                    >
                      {COLUMN_LABEL[col]}
                      <SortGlyph active={sort.key === col} dir={sort.dir} />
                    </button>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {sortedEvents.map((ev, i) => {
              const detailParts = [
                ev.reason ? `Reason: ${ev.reason}` : null,
                ev.thesis_id ? thesisById.get(ev.thesis_id)?.name ?? ev.thesis_id : null,
                ev.price != null ? `Price: $${Number(ev.price).toFixed(2)}` : null,
              ].filter(Boolean);
              const rowTitle = detailParts.length ? detailParts.join('\n') : undefined;
              return (
                <tr key={`${ev.date}-${ev.ticker}-${i}`} className="hover:bg-white/[0.02]" title={rowTitle}>
                  {orderedVisibleColumns.map((col) => renderCell(col, ev, i))}
                </tr>
              );
            })}
            {sortedEvents.length === 0 && (
              <tr>
                <td colSpan={colSpan} className="text-center py-10 text-text-muted">
                  {activityEvents.length === 0
                    ? 'No trades or rebalances in view.'
                    : 'No rows match filters or this date window. Widen the range or adjust filters.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
