'use client';

import { useMemo, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { DatePager } from '@digithings/web';
import type { FxBriefRow } from '@/lib/twelve-x/types';
import { sortTodayBriefs } from '@/lib/twelve-x/fetch';
import { adjacentDates } from '@/components/pipeline/PipelineDaySelector';
import { useTwelveX } from './context';

/** Distinct board run_dates present in a briefs window, newest first. */
export function availableBriefRunDates(briefs: FxBriefRow[]): string[] {
  const dates = new Set<string>();
  for (const b of briefs) {
    if (b.run_date) dates.add(b.run_date);
  }
  return Array.from(dates).sort().reverse();
}

/** Briefs for one board run_date, sorted like the Today slideshow. */
export function briefsForRunDate(briefs: FxBriefRow[], runDate: string): FxBriefRow[] {
  if (!runDate) return [];
  return sortTodayBriefs(briefs.filter((b) => b.run_date === runDate));
}

function resolveInitialDate(dates: string[], defaultDate: string | null): string {
  if (defaultDate && dates.includes(defaultDate)) return defaultDate;
  return dates[0] ?? '';
}

/**
 * Keep the user's date (including gap days with no briefs) when it falls inside
 * the board window. Only snap when empty or outside min/max after data changes.
 */
export function resolveActiveBoardDate(
  selectedDate: string,
  dates: string[],
  defaultDate: string | null,
): string {
  if (!selectedDate) return resolveInitialDate(dates, defaultDate);
  if (dates.length === 0) return selectedDate;
  const minDate = dates[dates.length - 1]!;
  const maxDate = dates[0]!;
  if (selectedDate >= minDate && selectedDate <= maxDate) return selectedDate;
  return resolveInitialDate(dates, defaultDate);
}

/**
 * Chevron targets for board dates (newest-first), including gap days: when the
 * calendar lands on a day with no briefs, jump to the nearest older/newer board.
 */
export function adjacentBriefBoardDates(
  dates: string[],
  value: string,
): { prev: string | null; next: string | null } {
  if (!value || dates.length === 0) return { prev: null, next: null };
  if (dates.includes(value)) return adjacentDates(dates, value);

  let prev: string | null = null;
  let next: string | null = null;
  for (const d of dates) {
    if (d < value && (prev === null || d > prev)) prev = d;
    if (d > value && (next === null || d < next)) next = d;
  }
  return { prev, next };
}

export default function BriefsIndex({
  briefs,
  defaultDate = null,
  onBack,
}: {
  briefs: FxBriefRow[];
  /** Canonical board date (latest digest / intelligence). */
  defaultDate?: string | null;
  onBack: () => void;
}) {
  const { openBrief } = useTwelveX();
  const dates = useMemo(() => availableBriefRunDates(briefs), [briefs]);
  const [selectedDate, setSelectedDate] = useState(() => resolveInitialDate(dates, defaultDate));

  const activeDate = resolveActiveBoardDate(selectedDate, dates, defaultDate);

  const dayBriefs = useMemo(
    () => briefsForRunDate(briefs, activeDate),
    [briefs, activeDate],
  );

  const minDate = dates.length ? dates[dates.length - 1] : undefined;
  const maxDate = dates.length ? dates[0] : undefined;
  const { prev, next } = adjacentBriefBoardDates(dates, activeDate);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex min-w-0 flex-wrap items-center gap-3">
        <button type="button" className="flex items-center gap-1 text-xs text-accent hover:underline" onClick={onBack}>
          <ArrowLeft size={14} /> Today
        </button>
        <h2 className="text-base font-semibold text-ink">Broker briefs</h2>
        <span className="font-mono text-[10px] text-ink-mute">
          {dayBriefs.length} {dayBriefs.length === 1 ? 'brief' : 'briefs'}
        </span>

        <div className="ml-auto flex min-w-0 items-center justify-end gap-3">
          <span className="font-mono text-xs font-medium uppercase text-ink-mute">Board date</span>
          <DatePager
            value={activeDate}
            onChange={setSelectedDate}
            min={minDate}
            max={maxDate}
            prevAriaLabel="Previous board date"
            nextAriaLabel="Next board date"
            labelAriaLabel="Filter briefs by board date"
            prevDisabled={!prev}
            nextDisabled={!next}
            onPrev={() => prev && setSelectedDate(prev)}
            onNext={() => next && setSelectedDate(next)}
            disabled={dates.length === 0}
          />
        </div>
      </header>

      {dayBriefs.length === 0 ? (
        <div className="oly-slab p-10 text-center text-sm text-ink-mute">
          {activeDate
            ? `No research briefs for ${activeDate}.`
            : 'No research briefs in this window yet.'}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {dayBriefs.map((b, i) => (
            <button
              key={`${b.source_file}-${b.run_date}-${i}`}
              type="button"
              className="oly-slab p-4 text-left transition-colors hover:border-accent/50"
              onClick={() => openBrief(b.source_file, b.run_date)}
            >
              <div className="flex min-w-0 items-center gap-2 text-[11px] text-ink-mute">
                <span className="min-w-0 truncate font-semibold text-ink-soft">
                  {b.broker_name ?? 'Unknown desk'}
                </span>
                {b.trader_relevance ? (
                  <span className="shrink-0 uppercase">· {b.trader_relevance}</span>
                ) : null}
              </div>
              <p className="mt-1 truncate text-sm font-medium text-ink">
                {b.document_title ?? b.source_file}
              </p>
              {b.central_thesis ? <p className="mt-1 line-clamp-3 text-xs text-ink-soft">{b.central_thesis}</p> : null}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
