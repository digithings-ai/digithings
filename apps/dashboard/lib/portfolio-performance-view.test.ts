import { describe, expect, it } from 'vitest';
import type { TableRow } from '@/lib/database.types';
import type { PerformanceHoldingRow } from '@/components/tearsheet/types';
import {
  alignedBenchmark,
  bridgeSteps,
  buildBookAttribution,
  drawdownFromReturns,
  excessReturns,
  navSummary,
  rangeStart,
  rankedContributions,
  realizedBars,
  rebaseReturns,
  signedPct,
  unrealizedBars,
  windowReturns,
} from './portfolio-performance-view';

const pts = (...v: Array<[string, number]>) => v.map(([date, returnPct]) => ({ date, returnPct }));

describe('rangeStart', () => {
  it('returns null for all and Jan 1 for ytd', () => {
    expect(rangeStart('all', '2026-09-30')).toBeNull();
    expect(rangeStart('ytd', '2026-09-30')).toBe('2026-01-01');
  });
  it('clamps month-end days when stepping back', () => {
    expect(rangeStart('1m', '2026-03-31')).toBe('2026-02-28');
    expect(rangeStart('3m', '2026-09-30')).toBe('2026-06-30');
    expect(rangeStart('1y', '2026-09-30')).toBe('2025-09-30');
  });
});

describe('rebaseReturns / windowReturns', () => {
  it('rebases so the first point is 0 and compounds correctly', () => {
    const out = rebaseReturns(pts(['2026-01-01', 10], ['2026-01-02', 21]));
    expect(out[0].returnPct).toBeCloseTo(0, 10);
    expect(out[1].returnPct).toBeCloseTo(10, 10); // 1.21 / 1.10 - 1
  });
  it('windows to the range ending at the series tip', () => {
    const out = windowReturns(
      pts(['2026-06-01', 5], ['2026-09-01', 8], ['2026-09-30', 12]),
      '1m'
    );
    expect(out.map((p) => p.date)).toEqual(['2026-09-01', '2026-09-30']);
    expect(out[0].returnPct).toBe(0);
  });
  it('returns [] on empty input', () => {
    expect(windowReturns([], 'all')).toEqual([]);
  });
});

describe('benchmark alignment and excess', () => {
  it('clips the benchmark to the window and rebases at the shared start', () => {
    const win = pts(['2026-09-01', 0], ['2026-09-30', 5]);
    const bench = pts(['2026-08-01', 3], ['2026-09-01', 10], ['2026-09-30', 21], ['2026-10-05', 40]);
    const out = alignedBenchmark(win, bench);
    expect(out.map((p) => p.date)).toEqual(['2026-09-01', '2026-09-30']);
    expect(out[1].returnPct).toBeCloseTo(10, 10);
  });
  it('computes excess only on shared dates', () => {
    const out = excessReturns(pts(['a', 5], ['b', 7]), pts(['b', 2]));
    expect(out).toEqual([{ date: 'b', returnPct: 5 }]);
  });
});

describe('drawdownFromReturns', () => {
  it('tracks peak-to-trough and the current distance below peak', () => {
    const dd = drawdownFromReturns(pts(['d1', 0], ['d2', 10], ['d3', -1.1], ['d4', 5.5]));
    expect(dd.series[1].returnPct).toBe(0);
    expect(dd.maxDrawdownPct).toBeCloseTo((0.989 / 1.1 - 1) * 100, 6);
    expect(dd.troughDate).toBe('d3');
    expect(dd.currentPct).toBeCloseTo((1.055 / 1.1 - 1) * 100, 6);
  });
  it('is zero for a monotonic rise', () => {
    const dd = drawdownFromReturns(pts(['a', 0], ['b', 1], ['c', 2]));
    expect(dd.maxDrawdownPct).toBe(0);
    expect(dd.troughDate).toBeNull();
  });
});

describe('rankedContributions', () => {
  it('ranks the last point by magnitude and keeps the sign', () => {
    const out = rankedContributions([
      { t: '2026-09-29', returnPct: 1, contributions: { AAA: 9 } },
      { t: '2026-09-30', returnPct: 2, contributions: { AAA: 0.5, BBB: -3, CCC: 1.5 } },
    ]);
    expect(out.asOf).toBe('2026-09-30');
    expect(out.total).toBe(2);
    expect(out.bars.map((b) => [b.label, b.value])).toEqual([
      ['BBB', -3],
      ['CCC', 1.5],
      ['AAA', 0.5],
    ]);
  });
  it('handles no points', () => {
    expect(rankedContributions([]).bars).toEqual([]);
  });
});

const holding = (over: Partial<PerformanceHoldingRow>): PerformanceHoldingRow => ({
  ticker: 'X',
  category: null,
  weightPct: null,
  unrealizedReturnPct: null,
  realizedReturnPct: null,
  attributionDate: null,
  ...over,
});

describe('unrealizedBars / realizedBars', () => {
  it('drops null returns instead of zeroing them', () => {
    const bars = unrealizedBars([
      holding({ ticker: 'A', unrealizedReturnPct: 4 }),
      holding({ ticker: 'B', unrealizedReturnPct: null }),
      holding({ ticker: 'C', unrealizedReturnPct: -9 }),
    ]);
    expect(bars.map((b) => b.label)).toEqual(['C', 'A']);
  });
  it('keeps repeated tickers distinct with disposition labels', () => {
    const bars = realizedBars([
      holding({ ticker: 'A', realizedReturnPct: 2, disposition: 'TRIM', attributionDate: '2026-01-02' }),
      holding({ ticker: 'A', realizedReturnPct: 5, disposition: 'EXIT', attributionDate: '2026-02-02' }),
    ]);
    expect(new Set(bars.map((b) => b.id)).size).toBe(2);
    expect(bars[0].label).toBe('A exit');
  });
});

type Row = TableRow<'position_attribution'>;
const row = (over: Partial<Row>): Row => ({
  id: over.ticker ?? 'id',
  date: '2026-09-30',
  ticker: 'AAA',
  sector_bucket: null,
  weight_pct: null,
  position_return_pct: null,
  benchmark_return_pct: 4,
  contribution_pct: null,
  selection_effect_pct: null,
  allocation_effect_pct: null,
  total_attribution_pct: null,
  metrics_as_of: null,
  created_at: null,
  ...over,
});

describe('buildBookAttribution', () => {
  it('returns null with no rows', () => {
    expect(buildBookAttribution([])).toBeNull();
  });

  it('builds a bridge that sums benchmark + active return and separates CASH allocation', () => {
    const view = buildBookAttribution([
      row({ ticker: 'AAA', contribution_pct: 3, selection_effect_pct: 1.5, total_attribution_pct: 1.5 }),
      row({ ticker: 'BBB', contribution_pct: -1, selection_effect_pct: -0.5, total_attribution_pct: -0.5 }),
      row({ ticker: 'CASH', allocation_effect_pct: -0.25, total_attribution_pct: -0.25 }),
    ]);
    expect(view?.holdings).toBe(2);
    expect(view?.unpriced).toBe(0);
    expect(view?.bridge?.selectionPct).toBeCloseTo(1, 10);
    expect(view?.bridge?.allocationPct).toBeCloseTo(-0.25, 10);
    expect(view?.bridge?.residualPct).toBeCloseTo(0, 10);
    expect(view?.bridge?.portfolioPct).toBeCloseTo(4.75, 10);
    expect(view?.contributors.map((b) => b.label)).toEqual(['AAA', 'BBB']);
  });

  it('has no bridge when no row carries a benchmark return, and counts unpriced holdings', () => {
    const view = buildBookAttribution([
      row({ ticker: 'AAA', benchmark_return_pct: null, total_attribution_pct: null }),
    ]);
    expect(view?.bridge).toBeNull();
    expect(view?.unpriced).toBe(1);
  });

  it('surfaces a residual when selection + allocation do not explain the active return', () => {
    const view = buildBookAttribution([
      row({ ticker: 'AAA', selection_effect_pct: 1, total_attribution_pct: 1.4 }),
    ]);
    expect(view?.bridge?.residualPct).toBeCloseTo(0.4, 10);
    const labels = bridgeSteps(view!.bridge!).map((s) => s.label);
    expect(labels).toEqual(['Benchmark', 'Selection', 'Cash alloc.', 'Residual', 'Portfolio']);
  });
});

describe('bridgeSteps', () => {
  it('omits the residual when immaterial and anchors totals at the ends', () => {
    const steps = bridgeSteps({
      benchmarkPct: 4,
      selectionPct: 1,
      allocationPct: -0.5,
      residualPct: 0,
      activePct: 0.5,
      portfolioPct: 4.5,
    });
    expect(steps.map((s) => s.kind)).toEqual(['total', 'delta', 'delta', 'total']);
    expect(steps[steps.length - 1].value).toBe(4.5);
  });
});

describe('text helpers', () => {
  it('signs percents and shows an em dash for null', () => {
    expect(signedPct(1.234)).toBe('+1.23%');
    expect(signedPct(-0.5)).toBe('-0.50%');
    expect(signedPct(null)).toBe('—');
  });
  it('summarises the NAV line and benchmark', () => {
    const s = navSummary(
      pts(['2026-09-01', 0], ['2026-09-30', 3.2]),
      pts(['2026-09-01', 0], ['2026-09-30', 1]),
      'SPY'
    );
    expect(s).toBe('Portfolio +3.20% from 2026-09-01 to 2026-09-30, SPY +1.00%.');
    expect(navSummary([], [], null)).toMatch(/Not enough/);
  });
});
