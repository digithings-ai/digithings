import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import BookReconciliationStrip from './BookReconciliationStrip';
import type { BookReconciliation, ReconciledPosition } from '@/lib/book-reconciliation';

const row = (ticker: string, w: number) => ({ ticker, normalizedWeight: w }) as unknown as ReconciledPosition;
const recon: BookReconciliation = {
  rows: [row('NVDA', 40), row('EWT', 35)],
  investedPct: 75,
  cashPct: 25,
  grossPct: 75,
  netPct: 75,
};
const render = (r: BookReconciliation = recon, n = 2) =>
  renderToStaticMarkup(createElement(BookReconciliationStrip, { reconciliation: r, asOfDate: '2026-06-23', positionCount: n }));

describe('BookReconciliationStrip', () => {
  it('renders kit Stat tiles for invested, cash and positions', () => {
    const html = render();
    expect(html).toContain('Invested');
    expect(html).toContain('75.0%');
    expect(html).toContain('Cash');
    expect(html).toContain('25.0%');
    expect(html).toContain('Positions');
    expect(html).toContain('>2<');
    expect(html).toContain('data-slot="stat"');
  });

  it('shows concentration: top position and top-5 share', () => {
    const html = render();
    expect(html).toContain('Top position');
    expect(html).toContain('40.0%');
    expect(html).toContain('NVDA');
    expect(html).toContain('75.0%'); // top 5 = 40 + 35
  });

  it('shows an em dash rather than a fabricated zero with no holdings', () => {
    const html = render({ ...recon, rows: [], investedPct: 0, cashPct: 100 }, 0);
    expect(html).toContain('none held');
  });

  it('keeps the as-of stamp and ledger doorway, with no up/down tone', () => {
    const html = render();
    expect(html).toContain('2026-06-23');
    expect(html).toContain('data-testid="command-band"');
    expect(html).toContain('data-testid="holdings-ledger-link"');
    expect(html).toContain('href="/portfolio/ledger"');
    expect(html).not.toContain('text-up');
    expect(html).not.toContain('text-down');
    expect(html).not.toContain('glass-card');
  });
});
