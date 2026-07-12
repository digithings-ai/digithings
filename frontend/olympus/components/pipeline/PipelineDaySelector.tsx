'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';

export interface PipelineDaySelectorProps {
  dates: string[];
  value: string;
  onChange: (date: string) => void;
}

export default function PipelineDaySelector({ dates, value, onChange }: PipelineDaySelectorProps) {
  const idx = dates.indexOf(value);
  const hasPrev = idx > 0;
  const hasNext = idx < dates.length - 1;

  const label = formatDate(value);

  return (
    <div className="ml-auto flex items-center gap-2 bg-term-bg border border-hair rounded-[9px] px-2.5 py-1.5 font-mono text-[12.5px] tabular-nums">
      <button
        type="button"
        aria-label="Previous day"
        disabled={!hasPrev}
        onClick={() => hasPrev && onChange(dates[idx - 1])}
        className="text-ink-mute hover:text-ink disabled:opacity-30 transition-colors"
      >
        <ChevronLeft size={14} />
      </button>

      <span className="text-ink whitespace-nowrap">{label}</span>

      <button
        type="button"
        aria-label="Next day"
        disabled={!hasNext}
        onClick={() => hasNext && onChange(dates[idx + 1])}
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
