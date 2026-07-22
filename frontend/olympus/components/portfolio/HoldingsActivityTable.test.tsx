import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import HoldingsActivityTable from './HoldingsActivityTable';
import type { DashboardPositionEvent } from '@/lib/types';

function event(index: number): DashboardPositionEvent {
  return {
    date: `2026-07-${String(index + 1).padStart(2, '0')}`,
    ticker: `T${String(index).padStart(2, '0')}`,
    event: index % 2 === 0 ? 'OPEN' : 'TRIM',
    weight_pct: 5,
    prev_weight_pct: index % 2 === 0 ? null : 6,
    weight_change_pct: index % 2 === 0 ? 5 : -1,
    price: 100 + index,
    thesis_id: null,
    reason: null,
  };
}

describe('HoldingsActivityTable', () => {
  it('renders the complete activity stream inside one scroll region', () => {
    const html = renderToStaticMarkup(
      createElement(HoldingsActivityTable, { events: Array.from({ length: 14 }, (_, index) => event(index)) })
    );

    expect(html).toContain('data-region="holdings-activity-scroll"');
    expect(html).toContain('T00');
    expect(html).toContain('T13');
    expect(html).not.toContain('Newer activity');
    expect(html).not.toContain('Older activity');
  });

  it('filters no-op HOLD events from the stream', () => {
    const html = renderToStaticMarkup(
      createElement(HoldingsActivityTable, {
        events: [{ ...event(0), ticker: 'KEEP', event: 'HOLD' }, event(1)],
      })
    );

    expect(html).not.toContain('KEEP');
    expect(html).toContain('T01');
  });
});