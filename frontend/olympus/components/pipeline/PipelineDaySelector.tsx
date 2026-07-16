'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';

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

export default function PipelineDaySelector({ dates, value, onChange }: PipelineDaySelectorProps) {
  const { prev, next } = adjacentDates(dates, value);

  const label = formatDate(value);

  return (
    <div className="ml-auto flex items-center gap-2 bg-term-bg border border-hair rounded-[9px] px-2.5 py-1.5 font-mono text-[12.5px] tabular-nums">
      <button
        type="button"
        aria-label="Previous day"
        disabled={!prev}
        onClick={() => prev && onChange(prev)}
        className="text-ink-mute hover:text-ink disabled:opacity-30 transition-colors"
      >
        <ChevronLeft size={14} />
      </button>

      <span className="text-ink whitespace-nowrap">{label}</span>

      <button
        type="button"
        aria-label="Next day"
        disabled={!next}
        onClick={() => next && onChange(next)}
        className="text-ink-mute hover:text-ink disabled:opacity-30 transition-colors"
      >
        <ChevronRight size={14} />
      </button>
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
