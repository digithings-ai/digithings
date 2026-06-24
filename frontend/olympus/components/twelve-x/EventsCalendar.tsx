'use client';

import { useMemo, useState } from 'react';
import { eventInstant, eventLocalDateKey } from '@/lib/twelve-x/fetch';
import { currencyColor } from '@/lib/twelve-x/consensus-bar';
import type { FxEconomicCalendarRow } from '@/lib/twelve-x/types';

/**
 * Month-grid calendar view of upcoming macro events. Ported from the frozen
 * twelve-x visual spec's `renderEvtCalendar`: a Sun→Sat 7-column grid where each
 * in-month day shows its number, impact dots, and an event count; days with
 * events are clickable and toggle a day-detail list below the grid.
 *
 * Date bucketing uses `eventLocalDateKey` (the same tz-consistent key the
 * timeline uses), and the grid is built with UTC date arithmetic so it renders
 * identically under SSR and across runner timezones.
 */

type ImpactLevel = 'high' | 'medium' | 'low';

export interface DayCell {
  /** ISO YYYY-MM-DD for this cell. */
  date: string;
  /** Day-of-month (1-31). */
  day: number;
  /** True when the cell belongs to the grid's target month. */
  inMonth: boolean;
  /** Number of events bucketed to this day. */
  count: number;
  /** Per-impact tallies for this day. */
  impacts: Record<ImpactLevel, number>;
}

export interface MonthGrid {
  /** Full year, e.g. 2026. */
  year: number;
  /** 1-based month, e.g. 6 for June. */
  month: number;
  /** Weeks (Sun→Sat), each exactly 7 cells. */
  weeks: DayCell[][];
}

/** Normalize the feed's free-text impact to the 3-level scale. */
function normalizeImpact(impact: string): ImpactLevel {
  const i = (impact ?? '').trim().toLowerCase();
  if (i === 'high') return 'high';
  if (i === 'medium' || i === 'med') return 'medium';
  return 'low';
}

/** Tailwind background token for an impact dot. */
function impactDotClass(impact: ImpactLevel): string {
  if (impact === 'high') return 'bg-fin-red';
  if (impact === 'medium') return 'bg-fin-amber';
  return 'bg-text-muted';
}

/** Parse a 'YYYY-MM' string into a 1-based {year, month}; defaults sanely. */
function parseMonth(month: string): { year: number; month: number } {
  const m = /^(\d{4})-(\d{2})$/.exec(month ?? '');
  if (!m) {
    const now = new Date();
    return { year: now.getUTCFullYear(), month: now.getUTCMonth() + 1 };
  }
  return { year: Number(m[1]), month: Number(m[2]) };
}

/** Zero-padded ISO date from UTC components (month/day are 1-based). */
function isoDate(year: number, month1: number, day: number): string {
  return `${year}-${String(month1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

/**
 * PURE — build a Sun→Sat month grid for `month` ('YYYY-MM'), bucketing `events`
 * onto their local-instant day. Leading days from the previous month and
 * trailing days from the next month fill out whole weeks and are flagged
 * `inMonth=false` (with a zero count). Uses `Date.UTC` so the layout is
 * deterministic regardless of the runner's timezone.
 */
export function buildMonthGrid(month: string, events: FxEconomicCalendarRow[]): MonthGrid {
  const { year, month: month1 } = parseMonth(month);

  // Bucket events by their tz-consistent local day key (matches the timeline).
  const counts = new Map<string, { count: number; impacts: Record<ImpactLevel, number> }>();
  for (const e of events) {
    const key = eventLocalDateKey(e);
    const bucket = counts.get(key) ?? { count: 0, impacts: { high: 0, medium: 0, low: 0 } };
    bucket.count += 1;
    bucket.impacts[normalizeImpact(e.impact)] += 1;
    counts.set(key, bucket);
  }

  const firstOfMonth = new Date(Date.UTC(year, month1 - 1, 1));
  const startDow = firstOfMonth.getUTCDay(); // 0 = Sun
  const daysInMonth = new Date(Date.UTC(year, month1, 0)).getUTCDate();

  // Start at the Sunday on/before the 1st; emit whole weeks until we've covered
  // the whole month (always a multiple of 7 cells).
  const start = new Date(Date.UTC(year, month1 - 1, 1 - startDow));
  const totalCells = Math.ceil((startDow + daysInMonth) / 7) * 7;

  const cells: DayCell[] = [];
  for (let i = 0; i < totalCells; i++) {
    const d = new Date(start.getTime() + i * 24 * 60 * 60 * 1000);
    const y = d.getUTCFullYear();
    const m1 = d.getUTCMonth() + 1;
    const day = d.getUTCDate();
    const date = isoDate(y, m1, day);
    const inMonth = y === year && m1 === month1;
    const bucket = counts.get(date);
    cells.push({
      date,
      day,
      inMonth,
      count: bucket?.count ?? 0,
      impacts: bucket?.impacts ?? { high: 0, medium: 0, low: 0 },
    });
  }

  const weeks: DayCell[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));

  return { year, month: month1, weeks };
}

const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;

/** UTC-stable "Tuesday, Jun 10" day label (matches the spec's dayLabel). */
function dayLabel(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

/** UTC-stable "June 2026" heading for the grid. */
function monthLabel(year: number, month1: number): string {
  const d = new Date(Date.UTC(year, month1 - 1, 1));
  return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });
}

/** Shift a 'YYYY-MM' by ±1 month. */
function shiftMonth(month: string, delta: number): string {
  const { year, month: month1 } = parseMonth(month);
  const d = new Date(Date.UTC(year, month1 - 1 + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

/** The 'HH:MM' a calendar row sits at (local instant, else wall-clock, else —). */
function rowTime(e: FxEconomicCalendarRow): string {
  const inst = eventInstant(e);
  if (inst) {
    const hh = String(inst.getHours()).padStart(2, '0');
    const mm = String(inst.getMinutes()).padStart(2, '0');
    return `${hh}:${mm}`;
  }
  const t = (e.event_time ?? '').trim();
  if (/^\d{1,2}:\d{2}/.test(t)) {
    const [h, m] = t.split(':');
    return `${h.padStart(2, '0')}:${m.slice(0, 2)}`;
  }
  return '—';
}

/** Compact "P:x · F:y · A:z" figures string (omits null/blank cells). */
function figs(e: FxEconomicCalendarRow): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];
  const add = (label: string, v: string | null) => {
    if (v != null && String(v).trim() !== '') out.push({ label, value: String(v) });
  };
  add('P', e.prior);
  add('F', e.forecast);
  add('A', e.actual);
  return out;
}

export interface EventsCalendarProps {
  events: FxEconomicCalendarRow[];
  /** Notified when a day with events is clicked. */
  onSelectDay?: (isoDate: string) => void;
  /** Pin the displayed month ('YYYY-MM') — used for deterministic SSR/tests. */
  initialMonth?: string;
}

export default function EventsCalendar({ events, onSelectDay, initialMonth }: EventsCalendarProps) {
  // The displayed month: the pinned `initialMonth`, else the month of the first
  // event, else the local current month — so the grid lands on data by default.
  const defaultMonth = useMemo(() => {
    if (initialMonth) return initialMonth;
    if (events.length > 0) {
      const key = eventLocalDateKey(events[0]);
      return key.slice(0, 7);
    }
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  }, [initialMonth, events]);

  const [month, setMonth] = useState(defaultMonth);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  const grid = useMemo(() => buildMonthGrid(month, events), [month, events]);

  // Day-detail rows for the selected day (sorted by time), bucketed by the same
  // local-day key the grid uses.
  const detailRows = useMemo(() => {
    if (!selectedDay) return [];
    return events
      .filter((e) => eventLocalDateKey(e) === selectedDay)
      .sort((a, b) => rowTime(a).localeCompare(rowTime(b)));
  }, [selectedDay, events]);

  const selectDay = (iso: string) => {
    setSelectedDay((cur) => (cur === iso ? null : iso));
    onSelectDay?.(iso);
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Month nav */}
      <div className="flex items-center justify-between px-1">
        <button
          type="button"
          onClick={() => {
            setMonth((m) => shiftMonth(m, -1));
            setSelectedDay(null);
          }}
          className="rounded-md border border-white/10 px-2.5 py-1 text-xs text-text-muted transition-colors hover:text-text-secondary"
          aria-label="Previous month"
        >
          ‹ Prev
        </button>
        <h3 className="text-sm font-semibold text-text-primary">
          {monthLabel(grid.year, grid.month)}
        </h3>
        <button
          type="button"
          onClick={() => {
            setMonth((m) => shiftMonth(m, 1));
            setSelectedDay(null);
          }}
          className="rounded-md border border-white/10 px-2.5 py-1 text-xs text-text-muted transition-colors hover:text-text-secondary"
          aria-label="Next month"
        >
          Next ›
        </button>
      </div>

      {/* Grid */}
      <div className="cal-grid grid grid-cols-7 gap-1.5">
        {DOW.map((d) => (
          <div
            key={d}
            className="pb-1 text-center text-[10px] uppercase tracking-[0.06em] text-text-muted"
          >
            {d}
          </div>
        ))}
        {grid.weeks.flat().map((cell) => {
          if (!cell.inMonth) {
            return (
              <div
                key={cell.date}
                className="aspect-square rounded-md border border-transparent"
                aria-hidden
              />
            );
          }
          const hasEvt = cell.count > 0;
          const selected = selectedDay === cell.date;
          const dots: ImpactLevel[] = [];
          for (let i = 0; i < cell.impacts.high; i++) dots.push('high');
          for (let i = 0; i < cell.impacts.medium; i++) dots.push('medium');
          for (let i = 0; i < cell.impacts.low; i++) dots.push('low');

          if (!hasEvt) {
            return (
              <div
                key={cell.date}
                className="flex aspect-square flex-col rounded-md border border-white/5 bg-white/[0.015] p-1.5"
              >
                <span className="font-mono text-[11px] text-text-secondary">{cell.day}</span>
              </div>
            );
          }

          return (
            <button
              key={cell.date}
              type="button"
              data-date={cell.date}
              onClick={() => selectDay(cell.date)}
              aria-pressed={selected}
              className={`has-evt flex aspect-square cursor-pointer flex-col rounded-md border p-1.5 text-left transition-colors ${
                selected
                  ? 'border-fin-blue/50 bg-fin-blue/10'
                  : 'border-white/5 bg-white/[0.015] hover:border-white/20'
              }`}
            >
              <span className="font-mono text-[11px] text-text-secondary">{cell.day}</span>
              <span className="mt-0.5 flex flex-wrap gap-[3px]">
                {dots.map((d, i) => (
                  <span
                    key={i}
                    className={`h-2 w-2 rounded-full ${impactDotClass(d)}`}
                    aria-hidden
                  />
                ))}
              </span>
              <span className="mt-auto text-[9.5px] text-text-muted">
                {cell.count} event{cell.count > 1 ? 's' : ''}
              </span>
            </button>
          );
        })}
      </div>

      {/* Day detail */}
      {selectedDay && detailRows.length > 0 ? (
        <div className="cal-detail glass-card overflow-hidden p-0">
          <div className="border-b border-border-subtle bg-bg-secondary px-4 py-2.5">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
              {dayLabel(selectedDay)}
            </h4>
          </div>
          <div className="divide-y divide-border-subtle">
            {detailRows.map((e) => {
              const impact = normalizeImpact(e.impact);
              return (
                <div key={e.id} className="flex items-center gap-3 px-4 py-2.5">
                  <span className="w-12 shrink-0 font-mono text-[13px] tabular-nums text-text-primary">
                    {rowTime(e)}
                  </span>
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${impactDotClass(impact)}`}
                    aria-hidden
                  />
                  <span
                    className="w-9 shrink-0 font-mono text-[12px] font-semibold"
                    style={{ color: currencyColor(e.country) }}
                  >
                    {e.country}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[13px] text-text-secondary">
                    {e.event_name}
                  </span>
                  <span className="shrink-0 whitespace-nowrap font-mono text-[11px] text-text-muted">
                    {figs(e).map((f, i) => (
                      <span key={f.label}>
                        {i > 0 ? ' · ' : ''}
                        {f.label}: <b className="font-semibold text-text-secondary">{f.value}</b>
                      </span>
                    ))}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
