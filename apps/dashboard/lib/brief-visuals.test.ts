import { describe, expect, it } from 'vitest';
import type { ReconciledPosition } from '@/lib/book-reconciliation';
import {
  compositionSegments,
  clipToRun,
  excessSeries,
  ledgerEventTone,
  moverItems,
  navSparkValues,
  rebalanceBullets,
  runSegmentCells,
  seriesStats,
  signedPctText,
  sparkValues,
  thesisStatusTone,
  trendTone,
  windowNavPoints,
} from './brief-visuals';

function pts(n: number, start = '2026-06-01') {
  const t0 = Date.parse(`${start}T00:00:00Z`);
  return Array.from({ length: n }, (_, i) => ({
    date: new Date(t0 + i * 86_400_000).toISOString().slice(0, 10),
    index: 100 + i,
  }));
}

const row = (ticker: string, w: number, day?: number): ReconciledPosition =>
  ({ ticker, name: ticker, normalizedWeight: w, day_change_pct: day }) as ReconciledPosition;

describe('series helpers', () => {
  it('windows to a trailing calendar range and keeps ALL whole', () => {
    const p = pts(120);
    expect(windowNavPoints(p, 'ALL')).toHaveLength(120);
    const m1 = windowNavPoints(p, '1M');
    expect(m1.length).toBeLessThan(40);
    expect(m1.at(-1)).toEqual(p.at(-1));
    expect(windowNavPoints(null, '3M')).toEqual([]);
  });

  it('drops non-finite points and sorts ascending', () => {
    const out = windowNavPoints(
      [
        { date: '2026-06-03', index: 3 },
        { date: '2026-06-01', index: 1 },
        { date: '2026-06-02', index: Number.NaN },
      ],
      'ALL'
    );
    expect(out.map((p) => p.index)).toEqual([1, 3]);
  });

  it('spark values need two points and cap at n', () => {
    expect(sparkValues([1], 30)).toEqual([]);
    expect(sparkValues([1, 2, 3, 4], 2)).toEqual([3, 4]);
    expect(navSparkValues(pts(50), 10)).toHaveLength(10);
    expect(navSparkValues([], 10)).toEqual([]);
  });

  it('stats: change, high/low, max drawdown', () => {
    const s = seriesStats([100, 110, 99, 105])!;
    expect(s.changePct).toBeCloseTo(5, 6);
    expect(s.high).toBe(110);
    expect(s.low).toBe(99);
    expect(s.maxDrawdownPct).toBeCloseTo(-10, 6);
    expect(seriesStats([100])).toBeNull();
    expect(seriesStats([0, 1])).toBeNull();
  });

  it('trend tone follows direction; short/flat is neutral', () => {
    expect(trendTone([1, 2])).toBe('up');
    expect(trendTone([2, 1])).toBe('down');
    expect(trendTone([1, 1])).toBe('ink');
    expect(trendTone([1])).toBe('ink');
  });
});

describe('excessSeries', () => {
  const nav = pts(30);
  const bench = nav.map((p, i) => ({ date: p.date, price: 500 + i }));

  it('rebases on the first shared date', () => {
    const s = excessSeries(nav, bench, 5);
    expect(s).toHaveLength(30);
    expect(s[0]).toBeCloseTo(0, 9);
    expect(s.at(-1)!).toBeGreaterThan(20);
  });

  it('fails closed on short overlap or missing benchmark', () => {
    expect(excessSeries(nav, bench.slice(0, 5), 20)).toEqual([]);
    expect(excessSeries(nav, [], 5)).toEqual([]);
    expect(excessSeries(nav, null)).toEqual([]);
  });
});

describe('excess across a NAV seam (#3935)', () => {
  // 20 legacy days on a ~100 basis, then a finalized run rebased to ~200.
  const legacy = pts(20);
  const finalized = pts(20).map((p, i) => ({
    date: new Date(Date.parse(legacy[19].date + 'T00:00:00Z') + (i + 1) * 86_400_000)
      .toISOString()
      .slice(0, 10),
    index: 200 + i * 0.1,
  }));
  const stitched = [...legacy, ...finalized];
  const bench = stitched.map((p, i) => ({ date: p.date, price: 500 + i * 0.5 }));
  const seamStart = finalized[0].date;

  it('unclipped series spans the seam (phantom jump)', () => {
    const s = excessSeries(stitched, bench, 5);
    expect(Math.max(...s.map(Math.abs))).toBeGreaterThan(50);
  });

  it('clipToRun rebases on the current run: starts at 0, no phantom jump', () => {
    const run = clipToRun(stitched, seamStart);
    expect(run[0].date).toBe(seamStart);
    expect(run).toHaveLength(20);
    const s = excessSeries(run, bench, 5);
    expect(s[0]).toBeCloseTo(0, 9);
    expect(Math.max(...s.map(Math.abs))).toBeLessThan(10);
  });

  it('clipToRun falls back to the full series without a usable start', () => {
    expect(clipToRun(stitched, null)).toHaveLength(40);
    expect(clipToRun(stitched, '2099-01-01')).toHaveLength(40);
  });
});

describe('composition / movers', () => {
  it('ranks by weight, folds the tail into Other, appends cash', () => {
    const held = [row('A', 5), row('B', 20), row('C', 10), row('D', 1)];
    const segs = compositionSegments(held, 64, 2);
    expect(segs.map((s) => s.label)).toEqual(['B', 'C', 'Other (2)', 'Cash']);
    expect(segs[2].value).toBe(6);
    expect(segs.at(-1)).toMatchObject({ cash: true, value: 64 });
  });

  it('omits cash when fully invested and skips zero weights', () => {
    const segs = compositionSegments([row('A', 100), row('Z', 0)], 0);
    expect(segs.map((s) => s.key)).toEqual(['A']);
  });

  it('movers rank by |day| and drop unknown', () => {
    const items = moverItems([row('A', 1, 0.4), row('B', 1, -5.64), row('C', 1), row('D', 1, 2)], 2);
    expect(items.map((m) => m.id)).toEqual(['B', 'D']);
    expect(items[0].display).toBe('-5.6%');
    expect(signedPctText(null)).toBe('—');
    expect(signedPctText(1.26)).toBe('+1.3%');
  });
});

describe('rebalanceBullets', () => {
  it('keeps only real changes with direction tone and a shared axis', () => {
    const out = rebalanceBullets([
      { ticker: 'nvda', current_pct: 8, recommended_pct: 6, action: 'TRIM' },
      { ticker: 'XLF', current_pct: 5, recommended_pct: 9, action: 'ADD' },
      { ticker: 'VGK', current_pct: 4, recommended_pct: 4, action: 'HOLD' },
    ]);
    expect(out.map((b) => b.ticker)).toEqual(['NVDA', 'XLF']);
    expect(out[0]).toMatchObject({ verb: 'Trim', tone: 'warn', text: '8.0% → 6.0%' });
    expect(out[1].tone).toBe('accent');
    expect(out[0].axisMax).toBe(out[1].axisMax);
    expect(out[0].axisMax).toBeGreaterThan(9);
  });
});

describe('runSegmentCells', () => {
  it('orders ok, carried, failed, unreported and uses health tones only', () => {
    const cells = runSegmentCells({
      segmentsOk: 3,
      segmentsTotal: 7,
      segmentsCarried: 1,
      segmentsFailed: 1,
    });
    expect(cells.map((c) => c.tone)).toEqual(['ok', 'ok', 'ok', 'off', 'warn', 'idle', 'idle']);
  });

  it('is empty without a known total; caps oversized totals', () => {
    expect(runSegmentCells(null)).toEqual([]);
    expect(
      runSegmentCells({ segmentsOk: 1, segmentsTotal: null, segmentsCarried: 0, segmentsFailed: 0 })
    ).toEqual([]);
    expect(
      runSegmentCells({ segmentsOk: 500, segmentsTotal: 500, segmentsCarried: 0, segmentsFailed: 0 })
    ).toHaveLength(48);
  });
});

describe('status tones', () => {
  it('maps thesis and ledger states to health tones', () => {
    expect(thesisStatusTone('ACTIVE')).toBe('ok');
    expect(thesisStatusTone('monitoring')).toBe('warn');
    expect(thesisStatusTone(null)).toBe('off');
    expect(ledgerEventTone('add')).toBe('ok');
    expect(ledgerEventTone('EXIT')).toBe('warn');
    expect(ledgerEventTone('HOLD')).toBe('off');
  });
});
