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
      meta: { last_updated: '2026-06-24', latest_snapshot_run_type: 'delta' },
      strategy: {
        regime: 'Risk-Off Consolidation',
        regime_label: 'caution',
        summary: 'Mixed signals persist as tech leads equities and USD strengthens.',
        actionable: [],
        risks: [],
        actionableItems: [
          { label: 'Monitor DXY above 120.4', priority: 1, rationale: 'near YTD highs' },
        ],
        riskItems: [
          { label: 'BOJ intervention', trigger: 'USD/JPY break above 162', horizonHours: 48 },
        ],
        theses: [{ id: 'T1', name: 'AI capex supercycle', status: 'ACTIVE', vehicle: null, confidence: 0.8 }],
        next_review: 'Daily',
      },
      snapshots: [
        { date: '2026-06-23', nav: 99.32 },
        { date: '2026-06-24', nav: 98.64 },
      ],
    },
    positions: [
      { ticker: 'EWT', name: 'EWT', weight_actual: 10, conviction: 3, day_change_pct: -5.64 },
      { ticker: 'UUP', name: 'UUP', weight_actual: 40, conviction: 2, day_change_pct: 0.32 },
      { ticker: 'CASH', name: 'CASH', weight_actual: 25 },
    ],
    portfolio_management: { rebalance_actions: actions },
    pipeline_observability: {},
    benchmarks: {
      SPY: { history: [{ date: '2026-06-23', price: 500 }, { date: '2026-06-24', price: 498 }] },
    },
    server_portfolio_metrics: { invested_pct: 75 },
  } as unknown as DashboardData;
}

describe('Today (Overview) page', () => {
  it('uses the shared content-shaped loading state', () => {
    useDashboardMock.mockReturnValue({ data: null, loading: true, error: null });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).toContain('aria-label="Loading page"');
  });

  it('uses the shared flat error state with one recovery action', () => {
    useDashboardMock.mockReturnValue({
      data: null,
      loading: false,
      error: 'Service unavailable',
    });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).toContain('data-slot="empty-state"');
    expect(html).toContain('Service unavailable');
    expect(html).toContain('Try again');
    expect(html).not.toContain('glass-card');
  });

  it('leads with the read, demotes the move, and shows honest NAV + all bands', () => {
    useDashboardMock.mockReturnValue({
      data: makeData([{ ticker: 'NVDA', current_pct: 8, recommended_pct: 6, action: 'TRIM' }]),
      loading: false,
      error: null,
    });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).toContain('Mixed signals persist'); // read marquee
    expect(html).toContain('since inception'); // honest NAV
    expect(html).toContain('1 change today'); // demoted move
    expect(html).toContain('Monitor DXY above 120.4'); // what to watch
    expect(html).toContain('BOJ intervention');
    expect(html).toContain('Invested'); // book strip reconciled header
    expect(html).toContain('EWT');
    expect(html).toContain('-5.6'); // biggest mover
    for (const label of ['The read', 'Holdings', 'Theses']) expect(html).toContain(label);
    expect(html).not.toContain("How I'"); // perf doorway retired
  });

  it('shows the holding-the-book status on a no-change day', () => {
    useDashboardMock.mockReturnValue({
      data: makeData([{ ticker: 'SPY', current_pct: 50, recommended_pct: 50, action: 'HOLD' }]),
      loading: false,
      error: null,
    });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).toContain('No rebalance today — holding the book');
  });

  it('keeps the localized regime accent, not a full-page wash', () => {
    useDashboardMock.mockReturnValue({ data: makeData([]), loading: false, error: null });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).not.toContain('inset_0_0_140px');
  });

  it('renders the populated brief as a section inside the app shell main', () => {
    useDashboardMock.mockReturnValue({ data: makeData([]), loading: false, error: null });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).toContain('data-testid="brief-workspace"');
    expect(html).toContain('aria-label="Daily investment brief"');
    expect(html).not.toContain('<main');
  });
});
