import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, it, expect, vi } from 'vitest';
import type { DashboardData } from '@/lib/types';

const { useDashboardMock } = vi.hoisted(() => ({ useDashboardMock: vi.fn() }));
const { useLiveBriefKpisMock } = vi.hoisted(() => ({ useLiveBriefKpisMock: vi.fn(() => null) }));
vi.mock('@/lib/dashboard-context', () => ({ useDashboard: () => useDashboardMock() }));
vi.mock('@/lib/hooks/use-live-brief-kpis', () => ({
  useLiveBriefKpis: () => useLiveBriefKpisMock(),
}));
vi.mock('next/link', () => ({
  default: (props: {
    children?: unknown;
    href?: string;
    className?: string;
    'data-testid'?: string;
    'aria-label'?: string;
  }) =>
    createElement(
      'a',
      {
        href: props.href,
        className: props.className,
        'data-testid': props['data-testid'],
        'aria-label': props['aria-label'],
      },
      props.children
    ),
}));

import { MIN_OVERLAP_DAYS } from '@digithings/web';
import OverviewPage from './page';

type Action = { ticker: string; current_pct: number; recommended_pct: number; action: string };

beforeEach(() => {
  useLiveBriefKpisMock.mockReturnValue(null);
});

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

function weekdayOverlap(
  count: number,
  startIso = '2026-05-04'
): Array<{ date: string; nav: number; price: number }> {
  const out: Array<{ date: string; nav: number; price: number }> = [];
  let nav = 100;
  let price = 500;
  const start = Date.parse(`${startIso}T00:00:00Z`);
  for (let i = 0; out.length < count; i++) {
    const d = new Date(start + i * 86_400_000);
    if (d.getUTCDay() === 0 || d.getUTCDay() === 6) continue;
    nav *= 1 + 0.001 + (out.length % 5) * 0.0003;
    price *= 1 + 0.0005 + (out.length % 7) * 0.0002;
    out.push({ date: d.toISOString().slice(0, 10), nav, price });
  }
  return out;
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

  it('orders the daily story from personal update through decisions, risk, and drill-ins', () => {
    useDashboardMock.mockReturnValue({
      data: makeData([{ ticker: 'NVDA', current_pct: 8, recommended_pct: 6, action: 'TRIM' }]),
      loading: false,
      error: null,
    });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).toContain('Your update');
    expect(html).toContain('data-testid="brief-attention"');
    // Attention prefers the book move when present; research beat keeps digest signal.
    expect(html).toContain('Trim NVDA');
    expect(html).toContain('Monitor DXY above 120.4');
    expect(html).toContain('Latest decision');
    expect(html).toContain('1 allocation change');
    expect(html).toContain('Pipeline health');
    expect(html).toContain('Checking pipeline status');
    expect(html).toContain('Since inception');
    expect(html).toContain('Alpha');
    expect(html).toContain('Info ratio');
    expect(html).toContain('Invested');
    expect(html).not.toContain('>NAV<');
    expect(html).not.toContain('Max drawdown');
    expect(html).not.toContain('Sharpe');
    expect(html).toContain('BOJ intervention');
    expect(html).toContain('AI capex supercycle');
    expect(html).toContain('Allocation and movers');
    expect(html).toContain('EWT');
    expect(html).toContain('-5.6');
    for (const label of ['Digest', 'Pipeline', 'Performance', 'Holdings', 'Theses']) {
      expect(html).toContain(label);
    }
    expect(html).not.toContain('Market state');
  });

  it('shows the holding-the-book status on a no-change day', () => {
    useDashboardMock.mockReturnValue({
      data: makeData([{ ticker: 'SPY', current_pct: 50, recommended_pct: 50, action: 'HOLD' }]),
      loading: false,
      error: null,
    });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).toContain('Holding the book');
    expect(html).toContain('No allocation change recommended');
  });

  it('keeps the localized regime accent, not a full-page wash', () => {
    useDashboardMock.mockReturnValue({ data: makeData([]), loading: false, error: null });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).not.toContain('inset_0_0_140px');
  });

  it('renders the populated brief as a section inside the app shell main', () => {
    useDashboardMock.mockReturnValue({ data: makeData([]), loading: false, error: null });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).toContain('data-testid="daily-brief-workspace"');
    expect(html).toContain('aria-label="Daily investment brief"');
    expect(html).not.toContain('<main');
  });

  it('surfaces live KPI excess/alpha/IR on the Brief scoreboard when SPY series exists', () => {
    useLiveBriefKpisMock.mockReturnValue({
      liveNav: 101.2,
      liveVsMarkPct: 0.5,
      priceAsOfDate: '2026-06-24',
      dayReturnPct: 0.3,
      sinceInceptionPct: 1.2,
      sinceInceptionStartDate: '2026-06-23',
      portfolioReturnPct: 1.2,
      benchmarkReturnPct: -0.6,
      excessReturnPct: 1.8,
      relativeGainPct: 1.8,
      alphaPct: 0.45,
      informationRatio: 0.32,
      benchmarkTicker: 'SPY',
      bookNavDate: '2026-06-24',
    });
    useDashboardMock.mockReturnValue({
      data: makeData([]),
      loading: false,
      error: null,
    });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).toContain('live marks');
    expect(html).toContain('vs SPY');
    expect(html).toContain('+1.8%');
    expect(html).toContain('+0.5%'); // alpha rounded via signedPct
    expect(html).toContain('0.32');
  });

  it('shows metrics-lag chrome when portfolio_metrics trails the book tip', () => {
    const data = makeData([]);
    data.portfolio.meta.last_updated = '2026-09-04';
    data.portfolio.snapshots = [
      {
        date: '2026-09-04',
        nav: 99.4,
        invested_pct: 40.5,
        contract: 'legacy_estimate',
        source: 'legacy_nav_history',
      },
    ];
    data.server_portfolio_metrics = {
      invested_pct: 79,
      date: '2026-09-01',
      as_of_date: '2026-09-01',
    };
    data.position_history = [{ date: '2026-09-04', ticker: 'SPY', weight_pct: 40, category: null, thesis_id: null }];
    data.positions = [
      { ticker: 'SPY', name: 'SPY', weight_actual: 40.5, conviction: 2, metrics_as_of: null },
    ];
    useDashboardMock.mockReturnValue({ data, loading: false, error: null });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).toContain('metrics lag');
    expect(html).toContain('marks unstamped');
    expect(html).toContain('accounting tip');
    expect(html).not.toContain('>79%<');
  });

  it('keeps persisted alpha/IR when live overlay is off and NAV/benchmark overlap is valid', () => {
    const series = weekdayOverlap(MIN_OVERLAP_DAYS + 5);
    const data = makeData([]);
    data.portfolio.snapshots = series.map((p) => ({
      date: p.date,
      nav: p.nav,
      invested_pct: 75,
      cash_pct: 25,
      contract: 'finalized_accounting',
      source: 'finalized_accounting',
    }));
    data.benchmarks = {
      SPY: { history: series.map((p) => ({ date: p.date, price: p.price })) },
    };
    useLiveBriefKpisMock.mockReturnValue({
      liveNav: 101.2,
      liveVsMarkPct: 0,
      priceAsOfDate: series.at(-1)!.date,
      dayReturnPct: 9.9,
      sinceInceptionPct: 9.9,
      sinceInceptionStartDate: series[0]!.date,
      portfolioReturnPct: 9.9,
      benchmarkReturnPct: 9.9,
      excessReturnPct: 9.9,
      relativeGainPct: 9.9,
      alphaPct: 99.9,
      informationRatio: 9.99,
      benchmarkTicker: 'SPY',
      bookNavDate: series.at(-1)!.date,
    });
    useDashboardMock.mockReturnValue({ data, loading: false, error: null });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).not.toContain('live marks');
    expect(html).not.toContain('99.9');
    expect(html).not.toContain('9.99');
    expect(html).not.toMatch(/>Alpha<\/dt><dd[^>]*>—</);
    expect(html).not.toMatch(/>Info ratio<\/dt><dd[^>]*>—</);
  });

  it('does not label live overlay numbers as finalized accounting', () => {
    const data = makeData([]);
    data.portfolio.snapshots = [
      {
        date: '2026-06-23',
        nav: 99.32,
        invested_pct: 75,
        cash_pct: 25,
        contract: 'finalized_accounting',
        source: 'finalized_accounting',
      },
      {
        date: '2026-06-24',
        nav: 98.64,
        invested_pct: 75,
        cash_pct: 25,
        contract: 'finalized_accounting',
        source: 'finalized_accounting',
      },
    ];
    useLiveBriefKpisMock.mockReturnValue({
      liveNav: 101.2,
      liveVsMarkPct: 0.5,
      priceAsOfDate: '2026-06-24',
      dayReturnPct: 0.3,
      sinceInceptionPct: 1.2,
      sinceInceptionStartDate: '2026-06-23',
      portfolioReturnPct: 1.2,
      benchmarkReturnPct: -0.6,
      excessReturnPct: 1.8,
      relativeGainPct: 1.8,
      alphaPct: 0.45,
      informationRatio: 0.32,
      benchmarkTicker: 'SPY',
      bookNavDate: '2026-06-24',
    });
    useDashboardMock.mockReturnValue({ data, loading: false, error: null });
    const html = renderToStaticMarkup(createElement(OverviewPage));
    expect(html).toContain('live marks');
    expect(html).not.toContain('finalized accounting');
  });
});
