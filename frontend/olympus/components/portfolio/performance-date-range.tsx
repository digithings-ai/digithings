'use client';

import { SegmentedControl } from '@digithings/web';
import type { DateRangeKey } from '@/lib/performance-series';

const OPTIONS: { value: DateRangeKey; label: string }[] = [
  { value: 'itd', label: 'ITD' },
  { value: 'ytd', label: 'YTD' },
  { value: '3m', label: '3M' },
  { value: '1m', label: '1M' },
];

/**
 * Rides the promoted @digithings/web SegmentedControl (dress="accent" —
 * olympus's shipped look) since #1548. The primitive also lands the a11y
 * fix: role="group" + aria-pressed replaces the previous role="tablist"
 * misuse (these segments switch a data range, they don't own tab panels).
 */
export function PerformanceDateRange({
  value,
  onChange,
}: {
  value: DateRangeKey;
  onChange: (k: DateRangeKey) => void;
}) {
  return (
    <SegmentedControl<DateRangeKey>
      dress="accent"
      className="flex flex-wrap"
      aria-label="Performance date range"
      options={OPTIONS}
      value={value}
      onChange={onChange}
    />
  );
}
