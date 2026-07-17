import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, it, expect, vi } from 'vitest';

let search = '';
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(search),
}));

import AllocationsPositionsTable from './AllocationsPositionsTable';
import type { BookReconciliation, ReconciledPosition } from '@/lib/book-reconciliation';
import type { Thesis } from '@/lib/types';
import type { TableRow } from '@/lib/database.types';

function pos(over: Partial<ReconciledPosition>): ReconciledPosition {
  return {
    ticker: 'NVDA', name: 'NVIDIA', type: 'LONG', weight_actual: 30, weight_target: null,
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
  positionHistory: [], positionEvents: [], thesisById: new Map<string, Thesis>(),
  lastUpdated: '2026-06-23', decisionByTicker: new Map<string, TableRow<'decision_log'>>(),
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

  it('groups rows under their sector_bucket header', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({ ticker: 'NVDA', sector_bucket: 'Technology' })]),
    }));
    expect(html).toContain('Technology');
  });

  it('drops the Name and Category column headers', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({})]),
    }));
    expect(html).not.toContain('>Name<');
    expect(html).not.toContain('>Category<');
  });

  it('shows a signed decision badge for a held position with a decision', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({ ticker: 'NVDA' })]),
      decisionByTicker: new Map([['NVDA', decision()]]),
    }));
    expect(html).toContain('+4');
    expect(html).toContain('/pipeline?'); // contextual deep-link
  });

  it('uses no off-palette blue/purple literals', () => {
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({})]),
    }));
    expect(html).not.toContain('59,130,246');
    expect(html).not.toContain('a78bfa');
  });

  it('expands a mixed-case ticker targeted by a deep link', () => {
    search = 'ticker=nvda';
    const html = renderToStaticMarkup(createElement(AllocationsPositionsTable, {
      ...baseProps, reconciliation: recon([pos({ ticker: 'Nvda' })]),
    }));
    expect(html).toContain('Avg entry');
  });
});
