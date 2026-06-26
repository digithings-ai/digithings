import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

import { BookStrip } from './book-strip';
import type { Position } from '@/lib/types';

function pos(p: Partial<Position> & { ticker: string }): Position {
  return {
    ticker: p.ticker, name: p.ticker, type: 'LONG', weight_actual: p.weight_actual ?? 10,
    current_price: null, entry_price: null, entry_date: null, rationale: '',
    thesis_ids: [], category: '', pm_notes: '', stats: {},
    conviction: p.conviction ?? null, day_change_pct: p.day_change_pct ?? null,
    sector_bucket: p.sector_bucket ?? null,
  } as Position;
}

describe('BookStrip', () => {
  const positions = [
    pos({ ticker: 'UUP', weight_actual: 40, conviction: 2, day_change_pct: 0.32 }),
    pos({ ticker: 'EWT', weight_actual: 10, conviction: 3, day_change_pct: -5.64 }),
    pos({ ticker: 'CASH', weight_actual: 25 }),
  ];
  it('shows the Invested/Cash header and leads with the biggest mover', () => {
    const html = renderToStaticMarkup(
      createElement(BookStrip, { positions, investedPct: 75, asOfDate: '2026-06-24' })
    );
    expect(html).toContain('Invested');
    expect(html).toContain('Cash');
    expect(html).toContain('EWT'); // biggest |move|
    expect(html).toContain('-5.6'); // its day move
    expect(html).toContain('All holdings'); // CTA to /portfolio
    // CASH is a header figure, not a list row
    expect(html.indexOf('EWT')).toBeLessThan(html.indexOf('UUP'));
  });
  it('renders an empty-state line when there are no held positions', () => {
    const html = renderToStaticMarkup(
      createElement(BookStrip, { positions: [pos({ ticker: 'CASH', weight_actual: 100 })], investedPct: 0, asOfDate: null })
    );
    expect(html).toContain('No positions held yet');
  });
});
