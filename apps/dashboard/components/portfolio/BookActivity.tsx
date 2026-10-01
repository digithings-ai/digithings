'use client';

import { CompositionBar, EmptyState } from '@digithings/ui/ui';
import type { DashboardPositionEvent } from '@/lib/types';
import { eventMix } from '@/lib/book-view';
import HoldingsActivityTable from '@/components/portfolio/HoldingsActivityTable';

const EVENT_TONE = { OPEN: 'accent', ADD: 'soft', TRIM: 'warn', EXIT: 'ink', HOLD: 'mute' } as const;

/** Position-event activity: a mix bar (what kind of moves) over the event table. */
export default function BookActivity({ events }: { events: DashboardPositionEvent[] }) {
  if (events.length === 0) {
    return (
      <EmptyState
        data-testid="book-activity-empty"
        variant="first-run"
        title="No position events recorded yet"
        body="Opens, adds, trims and exits appear here once the pipeline records a rebalance."
      />
    );
  }
  const mix = eventMix(events);
  return (
    <div data-testid="book-activity" className="space-y-3">
      <CompositionBar
        mode="share"
        legend
        label={`Position events by kind: ${mix.map((m) => `${m.label} ${m.value}`).join(', ')}`}
        segments={mix.map((m) => ({
          key: m.id,
          label: `${m.label} ${m.value}`,
          value: m.value,
          tone: EVENT_TONE[m.id as keyof typeof EVENT_TONE],
        }))}
      />
      <HoldingsActivityTable events={events} />
    </div>
  );
}
