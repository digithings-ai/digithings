import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';
import type { DashboardData } from '@/lib/types';

const { useDashboardMock } = vi.hoisted(() => ({ useDashboardMock: vi.fn() }));
vi.mock('@/lib/dashboard-context', () => ({ useDashboard: () => useDashboardMock() }));
vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

import OverviewPage from './page';

type Action = { ticker: string; current_pct: number; recommended_pct: number; action: string };

function makeData(actions: Action[]): DashboardData {
  return {
    portfolio: {
      meta: { last_updated: '2026-06-20', latest_snapshot_run_type: 'delta' },
      strategy: {
        regime: 'Risk-Off Consolidation',
        regime_label: 'neutral',
        summary: 'Risk-off consolidation; rotating into defensives.',
        theses: [{ id: 'T1', name: 'AI capex supercycle', status: 'confirmed', vehicle: 'NVDA' }],
      },
      // two snaps → sparkline skipped (deterministic SSR), navIndex = 104.2
      snapshots: [
        { date: '2026-04-12', nav: 100 },
        { date: '2026-06-20', nav: 104.2 },
      ],
    },
    positions: [{ ticker: 'NVDA', name: 'NVIDIA', weight_actual: 6.1, weight_delta: -2 }],
    portfolio_management: { rebalance_actions: actions },
    pipeline_observability: {
      deliberation_transcripts: [
        { ticker: 'NVDA', payload: { net_stance: 'bearish', conviction_delta: -3 } },
      ],
      pm_allocation_memo: 'Reducing beta into a stretched tape.',
      pm_rebalance: { actions: [{ ticker: 'NVDA', rationale: 'Valuation stretched into earnings.' }] },
    },
    benchmarks: {
      SPY: { history: [{ date: '2026-04-12', price: 500 }, { date: '2026-06-20', price: 510 }] },
    },
    server_portfolio_metrics: null,
  } as unknown as DashboardData;
}

describe('Today (Overview) page', () => {
  it('leads with the move above the NAV index and shows the four doorways', () => {
    useDashboardMock.mockReturnValue({
      data: makeData([{ ticker: 'NVDA', current_pct: 8, recommended_pct: 6, action: 'TRIM' }]),
      loading: false,
      error: null,
    });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).toContain('TRIM');
    expect(html.indexOf('TRIM')).toBeLessThan(html.indexOf('104.2'));
    for (const label of ['How I', 'The read', 'Holdings', 'Theses']) {
      expect(html).toContain(label);
    }
  });

  it('renders the HOLD-day hero without leaving it empty', () => {
    useDashboardMock.mockReturnValue({
      data: makeData([{ ticker: 'SPY', current_pct: 50, recommended_pct: 50, action: 'HOLD' }]),
      loading: false,
      error: null,
    });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).toContain('No changes proposed');
  });

  it('drops the legacy full-page regime ambient wash', () => {
    useDashboardMock.mockReturnValue({ data: makeData([]), loading: false, error: null });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).not.toContain('inset_0_0_140px');
  });
});
