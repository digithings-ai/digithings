import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import HoldingsActivityTable from './HoldingsActivityTable';
import type { DashboardPositionEvent } from '@/lib/types';

function event(index: number, overrides: Partial<DashboardPositionEvent> = {}): DashboardPositionEvent {
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
    avg_entry_price: 95,
    sold_weight_pct: index % 2 === 0 ? null : 1,
    realized_return_pct: index % 2 === 0 ? null : 5.26,
    ...overrides,
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

  it('surfaces avg entry, fill, and realized columns for sells', () => {
    const html = renderToStaticMarkup(
      createElement(HoldingsActivityTable, {
        events: [
          event(0, {
            ticker: 'GLD',
            event: 'TRIM',
            prev_weight_pct: 10,
            weight_pct: 5,
            weight_change_pct: -5,
            price: 199.5,
            avg_entry_price: 190,
            sold_weight_pct: 5,
            realized_return_pct: 5,
          }),
        ],
      })
    );

    expect(html).toContain('GLD');
    expect(html).toContain('TRIM');
    expect(html).toContain('-5.0pp');
    expect(html).toContain('$190.00');
    expect(html).toContain('$199.50');
    expect(html).toContain('+5.00%');
    expect(html).toContain('tap row for detail');
  });
});
