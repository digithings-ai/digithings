import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, it, expect, vi } from 'vitest';

let search = '';
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(search),
}));

import AllocationsPositionsTable from './AllocationsPositionsTable';
import type { BookReconciliation, ReconciledPosition } from '@/lib/book-reconciliation';
import type { TableRow } from '@/lib/database.types';

function pos(over: Partial<ReconciledPosition>): ReconciledPosition {
  return {
    ticker: 'NVDA', name: 'NVIDIA Corporation', type: 'LONG', weight_actual: 30, weight_target: null,
    weight_delta: null, current_price: 100, entry_price: 90, entry_date: null, rationale: '',
    thesis_ids: [], category: 'equity', pm_notes: '', stats: {}, normalizedWeight: 22.5,
    conviction: 3, sector_bucket: 'Technology', stop_loss_pct: -8, target_pct_gain: 15,
    horizon_days: 30, day_change_pct: 1.2, unrealized_pnl_pct: 11.1, ...over,
  };
}
const recon = (rows: ReconciledPosition[]): BookReconciliation => ({
  rows, investedPct: 75, cashPct: 25, grossPct: 75, netPct: 75,
});
const decision = () =>
  ({ ticker: 'NVDA', run_date: '2026-06-23', stance: 'buy', conviction: 4, status: 'pending' } as unknown as TableRow<'decision_log'>);
const baseProps = {
  decisionByTicker: new Map<string, TableRow<'decision_log'>>(),
};

describe('AllocationsPositionsTable', () => {
  beforeEach(() => {
    search = '';
  });

  it('renders normalized weights (not raw 150%-summing weight_actual)', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({ normalizedWeight: 22.5 })]),
    }));
    expect(html).toContain('22.5%');
    expect(html).not.toContain('30.0%');
  });

  it('shows the category directly in each position row', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({ ticker: 'NVDA', sector_bucket: 'Technology' })]),
    }));
    expect(html).toContain('Equity');
  });

  it('identifies each ticker with its canonical official name', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps,
      reconciliation: recon([pos({ ticker: 'NVDA', name: 'NVIDIA Corporation' })]),
    }));
    expect(html).toContain('NVDA');
    expect(html).toContain('NVIDIA Corporation');
    expect(html).toContain('title="NVIDIA Corporation"');
  });

  it('keeps only the requested monitoring columns', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({})]),
    }));
    expect(html).not.toContain('>Name<');
    expect(html).toContain('>Holding<');
    expect(html).toContain('>Category<');
    expect(html).toContain('>Allocation<');
    expect(html).toContain('>Conviction<');
    expect(html).toContain('>Day<');
    expect(html).toContain('>Unrealized<');
    expect(html).not.toContain('Δ vs target');
  });

  it('shows a signed decision badge for a held position with a decision', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({ ticker: 'NVDA' })]),
      decisionByTicker: new Map([['NVDA', decision()]]),
    }));
    expect(html).toContain('Decision');
    expect(html).toContain('/pipeline?'); // contextual deep-link
  });

  it('links every row to its ticker dossier, alongside the pipeline link (#1562 PR2)', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({ ticker: 'NVDA' })]),
      decisionByTicker: new Map([['NVDA', decision()]]),
    }));
    expect(html).toContain('/portfolio/tickers?ticker=NVDA');
    expect(html).toContain('/pipeline?'); // both links present, not a replacement
  });

  it('uses no off-palette blue/purple literals', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({})]),
    }));
    expect(html).not.toContain('59,130,246');
    expect(html).not.toContain('a78bfa');
  });

  it('highlights a mixed-case ticker targeted by a deep link without expanding it', () => {
    search = 'ticker=nvda';
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({ ticker: 'Nvda' })]),
    }));
    expect(html).toContain('data-selected="true"');
    expect(html).not.toContain('Avg entry');
  });

  it('uses canonical compact text on category and dossier link', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({})]),
    }));
    expect(html).toContain('text-xs text-ink-soft');
    expect(html).toContain('Dossier');
  });

  it('uses squared flat hairline ledger treatment instead of glass-card', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({})]),
    }));
    expect(html).not.toContain('glass-card');
    expect(html).not.toContain('rounded-lg');
    expect(html).toContain('border-hair');
  });

  it('has semantic structural selectors for test targeting', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({})]),
    }));
    expect(html).toContain('data-region="positions-table"');
    expect(html).toContain('table-fixed');
    expect(html).toContain('w-[175px]');
    expect(html).toContain('min-w-[980px]');
  });

  it('reserves a separate column when target weights are present', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({ weight_target: 20 })]),
    }));
    expect(html).toContain('min-w-[1080px]');
    expect(html.match(/<col/g)).toHaveLength(10); // colgroup plus nine columns
  });
});
