'use client';

import type { DateRangeKey } from '@/lib/performance-series';

const OPTIONS: { key: DateRangeKey; label: string }[] = [
  { key: 'itd', label: 'ITD' },
  { key: 'ytd', label: 'YTD' },
  { key: '3m', label: '3M' },
  { key: '1m', label: '1M' },
];

export function PerformanceDateRange({
  value,
  onChange,
}: {
  value: DateRangeKey;
  onChange: (k: DateRangeKey) => void;
}) {
  return (
    <div
      className="flex flex-wrap rounded-lg border border-hair overflow-hidden text-xs"
      role="tablist"
      aria-label="Performance date range"
    >
      {OPTIONS.map(({ key, label }, i) => (
        <button
          key={key}
          type="button"
          role="tab"
          aria-selected={value === key}
          onClick={() => onChange(key)}
          className={`px-3 py-1.5 font-medium transition-colors ${
            i > 0 ? 'border-l border-hair' : ''
          } ${value === key ? 'bg-accent/20 text-accent' : 'text-ink-mute hover:bg-white/[0.04] hover:text-ink'}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
