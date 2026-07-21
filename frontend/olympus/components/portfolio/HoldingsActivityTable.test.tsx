import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { DashboardPositionEvent } from '@/lib/types';
import HoldingsActivityTable from './HoldingsActivityTable';

vi.mock('next/link', () => ({
  default: ({ children, href, className }: React.ComponentProps<'a'>) =>
    createElement('a', { href, className }, children),
}));

function activity(index: number, event: DashboardPositionEvent['event'] = 'ADD') {
  return {
    date: `2026-07-${String(index).padStart(2, '0')}`,
    ticker: `T${String(index).padStart(2, '0')}`,
    event,
    weight_pct: index,
    prev_weight_pct: index - 1,
    weight_change_pct: 1,
    price: 100 + index,
    thesis_id: null,
    reason: null,
  } satisfies DashboardPositionEvent;
}

describe('HoldingsActivityTable', () => {
  it('filters HOLD rows and bounds the newest-first activity ledger to ten rows', () => {
    const events = [
      ...Array.from({ length: 12 }, (_, index) => activity(index + 1)),
      activity(13, 'HOLD'),
    ];

    const html = renderToStaticMarkup(createElement(HoldingsActivityTable, { events }));

    expect(html).toContain('data-region="holdings-activity"');
    expect(html).toContain('T12');
    expect(html).toContain('T03');
    expect(html).not.toContain('T02');
    expect(html).not.toContain('T01');
    expect(html).not.toContain('T13');
    expect(html).toContain('1 / 2');
  });

  it('renders an explicit empty state when there are no position changes', () => {
    const html = renderToStaticMarkup(
      createElement(HoldingsActivityTable, { events: [activity(1, 'HOLD')] })
    );

    expect(html).toContain('No position changes recorded.');
    expect(html).not.toContain('<table');
  });
});
