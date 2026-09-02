import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import BookReconciliationStrip from './BookReconciliationStrip';
import type { BookReconciliation } from '@/lib/book-reconciliation';

const recon: BookReconciliation = { rows: [], investedPct: 75, cashPct: 25, grossPct: 75, netPct: 75 };

describe('BookReconciliationStrip', () => {
  it('renders a slim summary with invested, cash, count, and ledger doorway', () => {
    const html = renderToStaticMarkup(
      createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: '2026-06-23', positionCount: 11 })
    );
    expect(html).toContain('Invested');
    expect(html).toContain('75.0%');
    expect(html).toContain('Cash');
    expect(html).toContain('25.0%');
    expect(html).not.toContain('gross');
    expect(html).not.toContain('net');
    expect(html).toContain('Positions');
    expect(html).toContain('2026-06-23');
    expect(html).toContain('data-testid="holdings-ledger-link"');
    expect(html).toContain('href="/portfolio/ledger"');
  });

  it('does not dominate the viewport with a giant invested figure', () => {
    const html = renderToStaticMarkup(
      createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: '2026-06-23', positionCount: 11 })
    );
    expect(html).not.toContain('text-5xl');
    expect(html).toContain('text-base');
  });

  it('uses a non-card command band with no glass-card', () => {
    const html = renderToStaticMarkup(
      createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: '2026-06-23', positionCount: 11 })
    );
    expect(html).not.toContain('glass-card');
    expect(html).toContain('border-hair');
    expect(html).toContain('data-testid="command-band"');
  });

  it('renders position count in the metrics strip', () => {
    const html = renderToStaticMarkup(
      createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: '2026-06-23', positionCount: 11 })
    );
    expect(html).toContain('Positions');
    expect(html).toContain('>11<');
  });

  it('uses identity, metrics, and as-of stamp regions', () => {
    const html = renderToStaticMarkup(
      createElement(BookReconciliationStrip, { reconciliation: recon, asOfDate: '2026-06-23', positionCount: 11 })
    );
    expect(html).toContain('data-region="identity"');
    expect(html).toContain('data-region="metrics"');
    expect(html).toContain('data-region="stamp"');
  });
});
