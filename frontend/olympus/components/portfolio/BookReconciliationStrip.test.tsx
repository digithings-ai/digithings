import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import BookReconciliationStrip from './BookReconciliationStrip';
import type { BookReconciliation } from '@/lib/book-reconciliation';

const recon: BookReconciliation = { rows: [], investedPct: 75, cashPct: 25, grossPct: 75, netPct: 75 };

describe('BookReconciliationStrip', () => {
  it('renders invested and cash that sum to 100', () => {
    const html = renderToStaticMarkup(
      createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: '2026-06-23' })
    );
    expect(html).toContain('Invested');
    expect(html).toContain('75.0%');
    expect(html).toContain('Cash');
    expect(html).toContain('25.0%');
    expect(html).toContain('2026-06-23');
  });

  it('omits the gross/net clause when unlevered (gross === invested)', () => {
    const html = renderToStaticMarkup(
      createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: null })
    );
    expect(html).not.toContain('Gross');
    expect(html).not.toContain('Net');
  });
});
