import { describe, expect, it } from 'vitest';
import { buildBookView, buildCorpusView, buildProfileView, houseFreshness } from './house-view';
import type { DeltaRequestMeta, Doc, NavChartPoint, Position } from './types';

const doc = (over: Partial<Doc>): Doc => ({
  id: 'x',
  date: '2026-09-01',
  title: 't',
  type: null,
  phase: null,
  category: null,
  segment: null,
  sector: null,
  runType: null,
  path: 'research/x.md',
  ...over,
});

const pos = (over: Partial<Position>): Position =>
  ({
    ticker: 'SPY',
    name: 'S',
    type: 'LONG',
    weight_actual: 10,
    current_price: null,
    entry_price: null,
    entry_date: null,
    rationale: '',
    ...over,
  }) as Position;

describe('buildCorpusView', () => {
  it('is empty-safe for DB-down', () => {
    const v = buildCorpusView(null);
    expect(v.total).toBe(0);
    expect(v.days).toEqual([]);
    expect(v.latestDate).toBeNull();
    expect(v.keyedPct).toBeNull();
    expect(v.deltaSharePct).toBeNull();
  });

  it('counts per day over a 53-week window ending at the latest doc', () => {
    const v = buildCorpusView([
      doc({ id: 'a', date: '2026-09-01' }),
      doc({ id: 'b', date: '2026-09-01' }),
      doc({ id: 'c', date: '2026-08-30', runType: 'delta' }),
      doc({ id: 'd', date: '2026-08-29', runType: 'baseline' }),
    ]);
    expect(v.days).toHaveLength(371);
    expect(v.days[v.days.length - 1]).toEqual({ date: '2026-09-01', count: 2 });
    expect(v.days.find((d) => d.date === '2026-08-31')?.count).toBe(0);
    expect(v.latestDate).toBe('2026-09-01');
    expect(v.daysCovered).toBe(3);
    expect(v.deltaSharePct).toBe(50);
    expect(v.weekly).toHaveLength(53);
    expect(v.weekly.reduce((a, b) => a + b, 0)).toBe(4);
  });

  it('measures keyed coverage from theme:/asset:/segment: paths and ranks classifiers', () => {
    const v = buildCorpusView([
      doc({ id: '1', path: 'theme:ai', category: 'macro', segment: 'equity' }),
      doc({ id: '2', path: 'asset:spy', category: 'macro' }),
      doc({ id: '3', path: 'notes/a.md', category: 'rates' }),
      doc({ id: '4', path: '' }),
    ]);
    expect(v.keyedCount).toBe(2);
    expect(v.sampleKeys).toEqual(['theme:ai', 'asset:spy']);
    expect(v.keyedPct).toBe(50);
    expect(v.byCategory[0]).toEqual({ label: 'macro', value: 2 });
    expect(v.bySegment).toEqual([{ label: 'equity', value: 1 }]);
  });

  it('unions changed paths over the last 7 covered days', () => {
    const meta: Record<string, DeltaRequestMeta> = {};
    for (let i = 1; i <= 9; i += 1) {
      meta[`2026-09-0${i}`] = { changed_paths: [`p${i}`, 'shared'], baseline_date: null, op_paths: [] };
    }
    const v = buildCorpusView([], meta);
    // days 03..09 -> p3..p9 + shared
    expect(v.changedPaths7d).toBe(8);
  });
});

describe('houseFreshness', () => {
  const now = new Date('2026-09-10T00:00:00Z');
  it('classifies fresh, stale and unknown', () => {
    expect(houseFreshness('2026-09-09T12:00:00Z', now).tone).toBe('ok');
    expect(houseFreshness('2026-09-01T00:00:00Z', now).tone).toBe('warn');
    expect(houseFreshness(null, now).tone).toBe('off');
    expect(houseFreshness('garbage', now).tone).toBe('off');
  });
});

describe('buildBookView', () => {
  it('rolls sleeves, drift and NAV return', () => {
    const snaps = [{ date: 'a', nav: 100 }, { date: 'b', nav: 110 }] as NavChartPoint[];
    const v = buildBookView(
      [
        pos({ ticker: 'A', category: 'Equity', weight_actual: 30, weight_target: 25 }),
        pos({ ticker: 'B', category: 'Equity', weight_actual: 20, weight_target: 20 }),
        pos({ ticker: 'C', type: 'SHORT',weight_actual: -10 }),
      ],
      snaps,
      40
    );
    expect(v.positionCount).toBe(3);
    expect(v.shortCount).toBe(1);
    expect(v.grossPct).toBe(60);
    expect(v.sleeves.map((s) => [s.label, s.value])).toEqual([
      ['Equity', 50],
      ['Uncategorised', 10],
    ]);
    expect(v.drifted).toBe(1);
    expect(v.navReturnPct).toBeCloseTo(10);
    expect(v.cashPct).toBe(40);
    expect(v.holdings[0].id).toBe('A');
  });

  it('returns nulls, not zeros, without data', () => {
    const v = buildBookView(undefined, undefined, undefined);
    expect(v.navReturnPct).toBeNull();
    expect(v.latestNav).toBeNull();
    expect(v.cashPct).toBeNull();
    expect(v.sleeves).toEqual([]);
  });
});

describe('buildProfileView', () => {
  it('lists universe, scalar constraints and a monotone tier grid', () => {
    const v = buildProfileView(
      [pos({ category: 'Rates' }), pos({ category: 'Equity' }), pos({ category: 'Rates' })],
      { max_position: 15, nested: { a: 1 }, long_only: false }
    );
    expect(v.universe).toEqual(['Equity', 'Rates']);
    expect(v.constraints).toEqual([
      { key: 'long_only', value: 'false' },
      { key: 'max_position', value: '15' },
    ]);
    const sums = v.grid.map((row) => row.reduce((a, b) => a + b, 0));
    expect(sums[0]).toBeLessThan(sums[v.tiers.indexOf('desk')]);
    expect(sums[v.tiers.indexOf('studio')]).toBe(v.classes.length);
  });
});
