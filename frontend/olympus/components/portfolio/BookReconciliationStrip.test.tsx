import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import BookReconciliationStrip from './BookReconciliationStrip';
import type { BookReconciliation } from '@/lib/book-reconciliation';

const recon: BookReconciliation = { rows: [], investedPct: 75, cashPct: 25, grossPct: 75, netPct: 75 };

describe('BookReconciliationStrip', () => {
  it('renders one exposure metric plus position count and date', () => {
    const html = renderToStaticMarkup(
      createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: '2026-06-23', positionCount: 11 })
    );
    expect(html).toContain('invested');
    expect(html).toContain('75.0%');
    expect(html).not.toContain('cash');
    expect(html).not.toContain('gross');
    expect(html).not.toContain('net');
    expect(html).toContain('positions');
    expect(html).toContain('2026-06-23');
  });

  it('does not duplicate exposure diagnostics in the command band', () => {
    const html = renderToStaticMarkup(
      createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: null, positionCount: 11 })
    );
    expect(html).not.toContain('cash');
    expect(html).not.toContain('gross');
    expect(html).not.toContain('net');
  });

  it('uses a non-card command band with a dominant Invested figure and no glass-card', () => {
    const html = renderToStaticMarkup(
      createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: '2026-06-23', positionCount: 11 })
    );
    expect(html).not.toContain('glass-card');
    expect(html).toContain('border-hair');
    expect(html).toContain('data-testid="command-band"');
  });

  it('renders position count in the metrics grid', () => {
    const html = renderToStaticMarkup(
      createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: '2026-06-23', positionCount: 11 })
    );
    expect(html).toContain('positions');
    expect(html).toContain('>11<');
  });

  it('uses a grid layout with identity, metrics, and as-of stamp', () => {
    const html = renderToStaticMarkup(
      createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: '2026-06-23', positionCount: 11 })
    );
    expect(html).toContain('data-region="identity"');
    expect(html).toContain('data-region="metrics"');
    expect(html).toContain('data-region="stamp"');
  });
});
