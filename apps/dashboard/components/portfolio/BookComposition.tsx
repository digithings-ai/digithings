'use client';

import { useMemo } from 'react';
import {
  AllocationTreemap,
  Button,
  DatePager,
  SegmentedControl,
  StackedAreaChart,
} from '@digithings/ui/ui';
import type { ReconciledPosition } from '@/lib/book-reconciliation';
import type { PositionHistoryRow, Thesis } from '@/lib/types';
import {
  COMPOSITION_MODES,
  CASH_ITEM_ID,
  compositionSummary,
  historicalComposition,
  liveComposition,
  type CompositionMode,
} from '@/lib/book-view';

export interface BookCompositionProps {
  rows: readonly ReconciledPosition[];
  cashPct: number;
  positionHistory: readonly PositionHistoryRow[];
  theses: readonly Thesis[];
  mode: CompositionMode;
  onModeChange: (m: CompositionMode) => void;
  /** Stacked weight history, already built for `mode` (lib/portfolio-aggregates). */
  sleeveData: Array<Record<string, number | string>>;
  sleeveKeys: string[];
  formatSleeveKey: (k: string) => string;
  /** The date the treemap shows; null = the live book. */
  effHistoryDate: string | null;
  dateParam: string | null;
  showHistoryDateBanner: boolean;
  onSelectHistoryDate: (iso: string) => void;
  onClearHistoryDate: () => void;
}

/**
 * Book composition: a treemap of what the book holds (area = weight) grouped by
 * ticker / category / thesis, and the weight history under it as a stacked area
 * whose columns set `?date=`. When a past date is pinned the treemap shows that
 * day's book and a banner says so, with a way back to the live book.
 */
export default function BookComposition({
  rows,
  cashPct,
  positionHistory,
  theses,
  mode,
  onModeChange,
  sleeveData,
  sleeveKeys,
  formatSleeveKey,
  effHistoryDate,
  dateParam,
  showHistoryDateBanner,
  onSelectHistoryDate,
  onClearHistoryDate,
}: BookCompositionProps) {
  const pinned = showHistoryDateBanner && dateParam ? dateParam : null;

  const items = useMemo(
    () =>
      pinned
        ? historicalComposition(positionHistory, pinned, mode, theses)
        : liveComposition(rows, cashPct, mode, theses),
    [pinned, positionHistory, rows, cashPct, mode, theses]
  );

  const dates = useMemo(
    () => sleeveData.map((r) => String(r.date ?? '')).filter(Boolean).sort(),
    [sleeveData]
  );
  const held = items.filter((i) => i.id !== CASH_ITEM_ID);
  const pagerValue = pinned ?? effHistoryDate ?? dates[dates.length - 1] ?? '';

  return (
    <section data-testid="book-composition" aria-label="Book composition" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-mono text-[0.68rem] uppercase tracking-wider text-ink-mute">
          {pinned ? `Composition on ${pinned}` : 'Composition now'}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <SegmentedControl
            dress="accent"
            aria-label="Group composition by"
            options={COMPOSITION_MODES}
            value={mode}
            onChange={onModeChange}
          />
          {dates.length > 1 ? (
            <DatePager
              value={pagerValue}
              onChange={onSelectHistoryDate}
              min={dates[0]}
              max={dates[dates.length - 1]}
              allowedDates={dates}
              prevAriaLabel="Previous date"
              nextAriaLabel="Next date"
              labelAriaLabel="Pick book date"
            />
          ) : null}
        </div>
      </div>

      {pinned ? (
        <div
          data-testid="history-date-banner"
          role="status"
          className="flex flex-wrap items-center justify-between gap-2 border border-hair bg-surface px-3 py-2 text-xs text-ink-soft"
        >
          <span>
            Showing the book as stored on <strong className="font-mono text-ink">{pinned}</strong>, not today&apos;s
            live weights.
          </span>
          <Button type="button" variant="outline" size="sm" onClick={onClearHistoryDate}>
            Back to live book
          </Button>
        </div>
      ) : null}

      <AllocationTreemap
        items={items}
        formatValue={(n) => `${Math.round(n * 10) / 10}%`}
        label={`Book composition by ${mode}. ${compositionSummary(items)}`}
        emptyLabel="No held positions to show."
      />
      <p className="sr-only" data-testid="book-composition-summary">
        {held.length} {held.length === 1 ? 'group' : 'groups'} held. {compositionSummary(items)}.
      </p>

      <div>
        <h3 className="mb-1 font-mono text-[0.68rem] uppercase tracking-wider text-ink-mute">
          Weight history · click a column to pin its date
        </h3>
        <StackedAreaChart
          data={sleeveData}
          keys={sleeveKeys.filter((k) => k !== 'cash')}
          cashKey={sleeveKeys.includes('cash') ? 'cash' : undefined}
          formatKey={formatSleeveKey}
          selectedX={pinned ?? effHistoryDate}
          onSelect={onSelectHistoryDate}
          label={`Weight history by ${mode}`}
          emptyLabel="Not enough position history to chart yet."
        />
      </div>
    </section>
  );
}
