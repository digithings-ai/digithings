'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Pager } from '@digithings/web';

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
 * Rides the promoted @digithings/web Pager (dress="capsule" — olympus's
 * shipped one-capsule look) since #1548; the temporal direction semantics
 * stay in `adjacentDates` above.
 */
export default function PipelineDaySelector({ dates, value, onChange }: PipelineDaySelectorProps) {
  const { prev, next } = adjacentDates(dates, value);

  return (
    <div className="flex items-center justify-between gap-3 lg:justify-end">
      <span className="font-mono text-xs font-medium uppercase text-ink-mute">
        Run date
      </span>
      <Pager
        dress="capsule"
        prevLabel={<ChevronLeft size={14} aria-hidden />}
        nextLabel={<ChevronRight size={14} aria-hidden />}
        prevAriaLabel="Previous day"
        nextAriaLabel="Next day"
        prevDisabled={!prev}
        nextDisabled={!next}
        onPrev={() => prev && onChange(prev)}
        onNext={() => next && onChange(next)}
      >
        <span className="whitespace-nowrap text-ink">{formatDate(value)}</span>
      </Pager>
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso + 'T12:00:00Z');
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  } catch {
    return iso;
  }
}
