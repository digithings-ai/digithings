import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { DashboardPositionEvent } from '@/lib/types';
import BookActivity from './BookActivity';

const ev = (event: DashboardPositionEvent['event'], ticker: string): DashboardPositionEvent => ({
  date: '2026-09-29',
  ticker,
  event,
  weight_pct: 10,
  prev_weight_pct: event === 'OPEN' ? 0 : 12,
  weight_change_pct: null,
  price: null,
  thesis_id: null,
  reason: null,
});

const render = (events: DashboardPositionEvent[]) =>
  renderToStaticMarkup(createElement(BookActivity, { events }));

describe('BookActivity', () => {
  it('uses the kit empty state when nothing has been recorded', () => {
    const html = render([]);
    expect(html).toContain('data-testid="book-activity-empty"');
    expect(html).toContain('data-slot="empty-state"');
    expect(html).toContain('No position events recorded yet');
    expect(html).not.toContain('data-testid="book-activity"');
  });

  it('summarises the event mix by kind in a stable order', () => {
    const html = render([ev('TRIM', 'EWT'), ev('OPEN', 'NVDA'), ev('OPEN', 'SPY')]);
    expect(html).toContain('data-testid="book-activity"');
    expect(html).toContain('Position events by kind: Open 2, Trim 1');
  });
});
