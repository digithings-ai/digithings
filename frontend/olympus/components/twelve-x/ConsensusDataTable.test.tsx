import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import type { ConsensusDeltaSet, FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import { ConsensusDataTable, passesFilter, type RowFilter } from './ConsensusDataTable';
import { LEAN_BAND, STRONG_BAND } from '@/lib/twelve-x/consensus-bar';
import { deriveConsensusRows } from '@/lib/twelve-x/consensus-view';

function snap(
  currency: string,
  run_date: string,
  score: number,
  extra: Partial<FxConsensusSnapshotRow> = {},
): FxConsensusSnapshotRow {
  return {
    run_date,
    currency,
    timeframe: 'medium',
    horizon_weeks: null,
    weighted: true,
    score,
    confidence: 0.7,
    agreement: 0.6,
    tilt: 0.1,
    n_eff: 5,
    n_brokers: 5,
    n_views: 8,
    bullish_pct: 0.5,
    bearish_pct: 0.3,
    neutral_pct: 0.1,
    watch_pct: 0.1,
    as_of: `${run_date}T12:00:00Z`,
    ...extra,
  };
}

function tenCurrencySeries(): FxConsensusSnapshotRow[] {
  const dates = [
    '2026-06-17',
    '2026-06-18',
    '2026-06-19',
    '2026-06-20',
    '2026-06-21',
    '2026-06-22',
  ];
  const rows: FxConsensusSnapshotRow[] = [];
  G10_CURRENCIES.forEach((currency, ci) => {
    dates.forEach((run_date, di) => {
      const score = (ci % 2 === 0 ? 1 : -1) * (0.3 + di * 0.2);
      rows.push(snap(currency, run_date, score));
    });
  });
  return rows;
}

function latestFrom(series: FxConsensusSnapshotRow[]): FxConsensusSnapshotRow[] {
  const byCcy = new Map<string, FxConsensusSnapshotRow>();
  for (const r of series) {
    const cur = byCcy.get(r.currency);
    if (!cur || r.run_date > cur.run_date) byCcy.set(r.currency, r);
  }
  return [...byCcy.values()];
}

const EMPTY_DELTAS: ConsensusDeltaSet = {
  runDate: null,
  prevRunDate: null,
  byCurrency: {},
  movers: [],
};

function render(
  series: FxConsensusSnapshotRow[],
  latest: FxConsensusSnapshotRow[],
  deltas: ConsensusDeltaSet = EMPTY_DELTAS,
  initialFilter?: RowFilter,
): string {
  return renderToStaticMarkup(
    createElement(ConsensusDataTable, { series, latest, deltas, initialFilter }),
  );
}

function renderedCcys(html: string): string[] {
  return [...html.matchAll(/data-ccy="([^"]+)"/g)].map((m) => m[1]);
}

describe('passesFilter', () => {
  it("'all' keeps every row regardless of score", () => {
    const series = tenCurrencySeries();
    const rows = deriveConsensusRows(series);
    for (const row of rows) {
      expect(passesFilter(row, 'all')).toBe(true);
    }
  });

  it("'bullish' keeps scores at/above +LEAN_BAND", () => {
    const series = tenCurrencySeries();
    const rows = deriveConsensusRows(series);
    const bullish = rows.filter((row) => passesFilter(row, 'bullish'));
    for (const row of bullish) {
      expect((row.actualNow ?? 0) >= LEAN_BAND).toBe(true);
    }
  });

  it("'bearish' keeps scores at/below -LEAN_BAND", () => {
    const series = tenCurrencySeries();
    const rows = deriveConsensusRows(series);
    const bearish = rows.filter((row) => passesFilter(row, 'bearish'));
    for (const row of bearish) {
      expect((row.actualNow ?? 0) <= -LEAN_BAND).toBe(true);
    }
  });

  it("'strong' keeps either-sign |score| >= STRONG_BAND", () => {
    const series = tenCurrencySeries();
    const rows = deriveConsensusRows(series);
    const strong = rows.filter((row) => passesFilter(row, 'strong'));
    for (const row of strong) {
      expect(Math.abs(row.actualNow ?? 0) >= STRONG_BAND).toBe(true);
    }
  });
});

describe('ConsensusDataTable component', () => {
  it('renders one table row per currency', () => {
    const series = tenCurrencySeries();
    const latest = latestFrom(series);
    const html = render(series, latest);
    const rows = renderedCcys(html);
    expect(rows).toHaveLength(G10_CURRENCIES.length);
  });

  it('renders filter buttons (All/Bullish/Bearish/Strong)', () => {
    const series = tenCurrencySeries();
    const latest = latestFrom(series);
    const html = render(series, latest);
    expect(html).toContain('data-filter="all"');
    expect(html).toContain('data-filter="bullish"');
    expect(html).toContain('data-filter="bearish"');
    expect(html).toContain('data-filter="strong"');
  });

  it('respects the initialFilter prop', () => {
    const series = tenCurrencySeries();
    const latest = latestFrom(series);
    const html = render(series, latest, EMPTY_DELTAS, 'bullish');
    expect(html).toMatch(/data-filter="bullish"[^>]*aria-pressed="true"/);
  });

  it('renders currency in canonical order', () => {
    const series = tenCurrencySeries();
    const latest = latestFrom(series);
    const html = render(series, latest);
    const rows = renderedCcys(html);
    expect(rows[0]).toBe('USD');
    expect(rows[1]).toBe('EUR');
  });
});
