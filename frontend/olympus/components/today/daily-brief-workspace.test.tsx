import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

import { DailyBriefWorkspace, type DailyBriefWorkspaceProps } from './daily-brief-workspace';
import type { DashboardPositionEvent, Position } from '@/lib/types';

const positions = [
  {
    ticker: 'XLF',
    name: 'Financials',
    type: 'LONG',
    weight_actual: 15.2,
    weight_delta: 0.1,
    current_price: null,
    entry_price: null,
    entry_date: null,
    rationale: '',
    thesis_ids: [],
    category: 'equity',
    pm_notes: '',
    stats: {},
    day_change_pct: -0.5,
  },
  {
    ticker: 'VGK',
    name: 'Europe',
    type: 'LONG',
    weight_actual: 15,
    weight_delta: 0,
    current_price: null,
    entry_price: null,
    entry_date: null,
    rationale: '',
    thesis_ids: [],
    category: 'equity',
    pm_notes: '',
    stats: {},
    day_change_pct: 0.4,
  },
  {
    ticker: 'CASH',
    name: 'Cash',
    type: 'CASH',
    weight_actual: 69.8,
    current_price: null,
    entry_price: null,
    entry_date: null,
    rationale: '',
    thesis_ids: [],
    category: 'cash',
    pm_notes: '',
    stats: {},
  },
] as Position[];

const latestEvent: DashboardPositionEvent = {
  date: '2026-08-05',
  ticker: 'XLF',
  event: 'ADD',
  weight_pct: 15.2,
  prev_weight_pct: 15.1,
  weight_change_pct: 0.1,
  price: null,
  thesis_id: null,
  reason: 'Maintain financial exposure while breadth confirms.',
};

const populatedProps: DailyBriefWorkspaceProps = {
  regime: 'Slowing / Cooling / Neutral / Risk-Off',
  regimeLabel: 'bearish',
  headline: 'Breadth improves while duration risk remains elevated.',
  confidence: 0.6,
  digestDate: '2026-08-06',
  bookDate: '2026-08-05',
  runType: 'delta',
  actions: [{ ticker: 'XLF', current_pct: 15.1, recommended_pct: 15.2, action: 'HOLD' }],
  rationaleByTicker: {},
  returns: {
    sincePct: -0.9,
    sinceDate: '2026-06-23',
    dailyPct: 0,
    dailyAsOf: '2026-08-05',
    sinceAsOf: '2026-08-05',
    benchTicker: 'SPY',
    excessPct: 1.8,
    excessAsOf: '2026-08-05',
    alphaPct: 0.4,
    informationRatio: 0.35,
  },
  metrics: { maxDrawdown: -2.4, volatility: 11.8 },
  investedPct: 30.2,
  positions,
  actionables: [{ label: 'Hold breadth above 65%', priority: 1, rationale: 'Confirms participation.' }],
  risks: [{ label: 'Duration selloff', trigger: '10Y above 4.80%', horizonHours: 48 }],
  theses: [{ id: 'T1', name: 'International breadth is improving', status: 'active' }],
  contextBullets: ['Gold strength conflicts with the risk-on breadth signal.'],
  latestEvent,
  runHealth: {
    status: 'completed',
    runDate: '2026-08-06',
    finishedAt: '2026-08-06T12:45:00Z',
    segmentsOk: 8,
    segmentsTotal: 8,
    segmentsCarried: 0,
    segmentsFailed: 0,
  },
};

const emptyProps: DailyBriefWorkspaceProps = {
  regime: 'Unknown',
  regimeLabel: 'neutral',
  headline: null,
  confidence: null,
  digestDate: null,
  bookDate: null,
  runType: null,
  actions: [],
  rationaleByTicker: {},
  returns: {
    sincePct: null,
    sinceDate: null,
    dailyPct: null,
    dailyAsOf: null,
    sinceAsOf: null,
    benchTicker: null,
    excessPct: null,
    excessAsOf: null,
    alphaPct: null,
    informationRatio: null,
  },
  metrics: { maxDrawdown: null, volatility: null },
  investedPct: null,
  positions: [],
  actionables: [],
  risks: [],
  theses: [],
  contextBullets: [],
  latestEvent: null,
  runHealth: null,
};

describe('DailyBriefWorkspace', () => {
  it('tells the daily monitoring story once, with an honest system state and drill-ins', () => {
    const html = renderToStaticMarkup(
      <DailyBriefWorkspace {...populatedProps} />
    );

    expect(html).toContain('Morning brief');
    expect(html).toContain('Breadth improves while duration risk remains elevated.');
    expect(html).toContain('Holding the book');
    expect(html).toContain('Pipeline complete');
    expect(html).toContain('8 / 8 segments');
    expect(html).toContain('Alpha');
    expect(html).toContain('+0.4%');
    expect(html).toContain('Info ratio');
    expect(html).toContain('0.35');
    expect(html).not.toContain('Max drawdown');
    expect(html).not.toContain('Volatility');
    expect(html).toContain('Invested');
    expect(html).toContain('30%');
    expect(html).not.toContain('>NAV<');
    expect(html).not.toContain('98.5');
    expect(html).not.toContain('Sharpe');
    expect(html).toContain('Duration selloff');
    expect(html).toContain('International breadth is improving');
    expect(html).toContain('Gold strength conflicts');
    expect(html).toContain('Maintain financial exposure');
    expect(html).toContain('XLF');
    expect(html).toContain('VGK');
    expect(html.match(/Breadth improves while duration risk remains elevated\./g)).toHaveLength(1);
    expect(html).toContain('Pipeline');
    expect(html).toContain('Performance');
    expect(html).toContain('Holdings');
    expect(html).toContain('Theses');
    expect(html).toContain('data-testid="daily-brief-workspace"');
    expect(html).toContain('line-clamp-6');
    expect(html).toContain('Open digest');
    expect(html).toContain('overflow-x-auto');
    expect(html).not.toContain('glass-card');
  });

  it('does not imply a healthy pipeline when run telemetry is unavailable', () => {
    const html = renderToStaticMarkup(
      <DailyBriefWorkspace {...emptyProps} />
    );

    expect(html).toContain('Pipeline status unavailable');
    expect(html).not.toContain('Pipeline complete');
    expect(html).toContain('No book decision recorded');
    expect(html).toContain('No additional digest context was recorded.');
  });
});