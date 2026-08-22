'use client';

import { useMemo, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import type { FxBriefRow } from '@/lib/twelve-x/types';
import { sortTodayBriefs } from '@/lib/twelve-x/fetch';
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

  // If the window loads/changes and the selection is empty or stale, snap to default/latest.
  const activeDate = dates.includes(selectedDate)
    ? selectedDate
    : resolveInitialDate(dates, defaultDate);

  const dayBriefs = useMemo(
    () => briefsForRunDate(briefs, activeDate),
    [briefs, activeDate],
  );

  const minDate = dates.length ? dates[dates.length - 1] : undefined;
  const maxDate = dates.length ? dates[0] : undefined;

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center gap-3">
        <button type="button" className="flex items-center gap-1 text-xs text-accent hover:underline" onClick={onBack}>
          <ArrowLeft size={14} /> Today
        </button>
        <h2 className="text-base font-semibold text-ink">Broker briefs</h2>
        <label className="ml-auto flex items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink-mute">Board date</span>
          <input
            type="date"
            value={activeDate}
            min={minDate}
            max={maxDate}
            disabled={dates.length === 0}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="rounded-md border border-hair bg-term-bg px-2 py-1.5 font-mono text-xs text-ink focus:outline-none focus:ring-1 focus:ring-inset focus:ring-accent/30"
            aria-label="Filter briefs by board date"
          />
        </label>
        <span className="font-mono text-[10px] text-ink-mute">{dayBriefs.length}</span>
      </header>

      {dates.length > 1 ? (
        <div className="flex flex-wrap gap-1.5" role="list" aria-label="Available board dates">
          {dates.map((d) => {
            const selected = d === activeDate;
            return (
              <button
                key={d}
                type="button"
                role="listitem"
                onClick={() => setSelectedDate(d)}
                className={
                  selected
                    ? 'rounded border border-accent/60 bg-accent/10 px-2 py-1 font-mono text-[11px] text-accent'
                    : 'rounded border border-hair bg-term-bg px-2 py-1 font-mono text-[11px] text-ink-mute hover:border-accent/40 hover:text-ink-soft'
                }
                aria-pressed={selected}
              >
                {d}
              </button>
            );
          })}
        </div>
      ) : null}

      {dayBriefs.length === 0 ? (
        <div className="glass-card p-10 text-center text-sm text-ink-mute">
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
              className="glass-card p-4 text-left transition-colors hover:border-accent/50"
              onClick={() => openBrief(b.source_file, b.run_date)}
            >
              <div className="flex items-center gap-2 text-[11px] text-ink-mute">
                <span className="font-semibold text-ink-soft">{b.broker_name ?? 'Unknown desk'}</span>
                {b.trader_relevance ? <span className="uppercase">· {b.trader_relevance}</span> : null}
              </div>
              <p className="mt-1 text-sm font-medium text-ink">{b.document_title ?? b.source_file}</p>
              {b.central_thesis ? <p className="mt-1 line-clamp-3 text-xs text-ink-soft">{b.central_thesis}</p> : null}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
