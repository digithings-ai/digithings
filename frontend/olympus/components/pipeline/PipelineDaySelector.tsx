'use client';

import { DatePager } from '@digithings/web';

export interface PipelineDaySelectorProps {
  /** Available run dates, newest first (PipelineClient sorts descending). */
  dates: string[];
  value: string;
  onChange: (date: string) => void;
}

/**
 * Chevron targets against a NEWEST-FIRST date list: "previous" (chevron-left)
 * is the chronologically older day = the HIGHER index; "next" is the newer
 * day = the LOWER index. Exported for unit tests — the original index math
 * assumed an ascending list and shipped with the arrows inverted (#1538).
 */
export function adjacentDates(
  dates: string[],
  value: string,
): { prev: string | null; next: string | null } {
  const idx = dates.indexOf(value);
  if (idx === -1) return { prev: null, next: null };
  return {
    prev: idx < dates.length - 1 ? dates[idx + 1] : null,
    next: idx > 0 ? dates[idx - 1] : null,
  };
}

/**
 * Pipeline run-date control — same DatePager capsule + calendar as BriefsIndex
 * (shared @digithings/web). Discrete `allowedDates` so the calendar only lands
 * on days that have a run.
 */
export default function PipelineDaySelector({ dates, value, onChange }: PipelineDaySelectorProps) {
  const { prev, next } = adjacentDates(dates, value);
  const minDate = dates.length ? dates[dates.length - 1] : undefined;
  const maxDate = dates.length ? dates[0] : undefined;

  return (
    <div className="flex items-center justify-between gap-3 lg:justify-end">
      <span className="font-mono text-xs font-medium uppercase text-ink-mute">
        Run date
      </span>
      <DatePager
        value={value}
        onChange={onChange}
        min={minDate}
        max={maxDate}
        allowedDates={dates}
        prevAriaLabel="Previous day"
        nextAriaLabel="Next day"
        labelAriaLabel="Pick run date"
        prevDisabled={!prev}
        nextDisabled={!next}
        onPrev={() => prev && onChange(prev)}
        onNext={() => next && onChange(next)}
        disabled={dates.length === 0}
      />
    </div>
  );
}
