import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import type { ConsensusDeltaSet, FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import {
  ConsensusDataTable,
  avgWindow,
  passesFilter,
  sortRows,
  vsAvg,
  type ConsensusTableRow,
  type RowFilter,
} from './ConsensusDataTable';
import { LEAN_BAND, STRONG_BAND } from '@/lib/twelve-x/consensus-bar';

/** Minimal snapshot-row factory; only the fields the table reads are varied. */
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

/**
 * A 6-run ascending series for every G10 currency. Even-indexed currencies
 * (USD…) trend bullish, odd-indexed (EUR…) trend bearish, so filters and sorts
 * have something to bite on.
 */
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

/** The latest snapshot for each currency (last run_date in the fixture). */
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

/** Currency codes of the rendered body rows, in render order. */
function renderedCcys(html: string): string[] {
  return [...html.matchAll(/data-ccy="([^"]+)"/g)].map((m) => m[1]);
}

/* ----------------------------------------------------------------------- */
/* Pure helper: avgWindow                                                  */
/* ----------------------------------------------------------------------- */

describe('avgWindow', () => {
  // EUR has scores -0.3,-0.5,-0.7,-0.9,-1.1,-1.3 across the 6 runs (ascending).
  const series = tenCurrencySeries();

  it('takes the trailing-window mean of a currency score series (window 3)', () => {
    // Trailing 3 of EUR: (-0.9 + -1.1 + -1.3) / 3 = -1.1
    expect(avgWindow(series, 'EUR', 3)).toBeCloseTo(-1.1, 10);
  });

  it('takes the trailing-window mean (window 5) — a DIFFERENT value than window 3', () => {
    // Trailing 5 of EUR: (-0.5 -0.7 -0.9 -1.1 -1.3) / 5 = -0.9
    const w5 = avgWindow(series, 'EUR', 5);
    expect(w5).toBeCloseTo(-0.9, 10);
    // Changing the window MUST recompute to a different number.
    expect(w5).not.toBeCloseTo(avgWindow(series, 'EUR', 3) as number, 6);
  });

  it('averages all available points when the window exceeds the series length', () => {
    // Window 20 over only 6 EUR points: full mean = -0.8
    expect(avgWindow(series, 'EUR', 20)).toBeCloseTo(-0.8, 10);
  });

  it('sorts by run_date ascending regardless of input order before windowing', () => {
    // Shuffle EUR rows so the latest run is NOT last in input order.
    const shuffled = [
      snap('EUR', '2026-06-22', -1.3),
      snap('EUR', '2026-06-17', -0.3),
      snap('EUR', '2026-06-21', -1.1),
      snap('EUR', '2026-06-19', -0.7),
    ];
    // Trailing 3 by date = runs 19, 21, 22 → (-0.7 -1.1 -1.3)/3 = -1.0333…
    expect(avgWindow(shuffled, 'EUR', 3)).toBeCloseTo((-0.7 - 1.1 - 1.3) / 3, 10);
  });

  it('returns null for a currency with no rows', () => {
    expect(avgWindow(series, 'ZZZ', 5)).toBeNull();
  });

  it('skips non-finite scores rather than poisoning the mean', () => {
    const withBad = [
      snap('XAU', '2026-06-20', 1.0),
      snap('XAU', '2026-06-21', Number.NaN),
      snap('XAU', '2026-06-22', 2.0),
    ];
    // Trailing 3 with NaN skipped: (1.0 + 2.0) / 2 = 1.5
    expect(avgWindow(withBad, 'XAU', 3)).toBeCloseTo(1.5, 10);
  });
});

/* ----------------------------------------------------------------------- */
/* Pure helper: vsAvg                                                      */
/* ----------------------------------------------------------------------- */

describe('vsAvg', () => {
  it('flags actual above the average', () => {
    expect(vsAvg(1.0, 0.5)).toBe('above');
  });

  it('flags actual below the average', () => {
    expect(vsAvg(0.2, 0.9)).toBe('below');
  });

  it('treats a sub-epsilon gap as equal', () => {
    expect(vsAvg(0.5001, 0.5)).toBe('equal');
  });

  it('returns null when either side is null', () => {
    expect(vsAvg(null, 0.5)).toBeNull();
    expect(vsAvg(0.5, null)).toBeNull();
    expect(vsAvg(null, null)).toBeNull();
  });

  it('returns null for non-finite inputs', () => {
    expect(vsAvg(Number.NaN, 0.5)).toBeNull();
  });
});

/* ----------------------------------------------------------------------- */
/* Pure helper: passesFilter                                               */
/* ----------------------------------------------------------------------- */

describe('passesFilter', () => {
  const at = (score: number): ConsensusTableRow => row({ score });

  it("'all' keeps every row regardless of score", () => {
    for (const s of [-2, -STRONG_BAND, -LEAN_BAND, 0, LEAN_BAND, STRONG_BAND, 2]) {
      expect(passesFilter(at(s), 'all')).toBe(true);
    }
  });

  it("'bullish' keeps scores at/above +LEAN_BAND and rejects below it", () => {
    expect(passesFilter(at(LEAN_BAND), 'bullish')).toBe(true); // boundary is inclusive
    expect(passesFilter(at(LEAN_BAND + 0.5), 'bullish')).toBe(true);
    expect(passesFilter(at(LEAN_BAND - 0.01), 'bullish')).toBe(false);
    expect(passesFilter(at(0), 'bullish')).toBe(false);
    // A bearish (negative) score must NOT pass the bullish filter.
    expect(passesFilter(at(-LEAN_BAND), 'bullish')).toBe(false);
  });

  it("'bearish' keeps scores at/below -LEAN_BAND and rejects above it", () => {
    expect(passesFilter(at(-LEAN_BAND), 'bearish')).toBe(true); // boundary is inclusive
    expect(passesFilter(at(-LEAN_BAND - 0.5), 'bearish')).toBe(true);
    expect(passesFilter(at(-LEAN_BAND + 0.01), 'bearish')).toBe(false);
    expect(passesFilter(at(0), 'bearish')).toBe(false);
    // A bullish (positive) score must NOT pass the bearish filter.
    expect(passesFilter(at(LEAN_BAND), 'bearish')).toBe(false);
  });

  it("'strong' keeps either-sign |score| >= STRONG_BAND and rejects sub-band magnitudes", () => {
    expect(passesFilter(at(STRONG_BAND), 'strong')).toBe(true); // boundary is inclusive
    expect(passesFilter(at(-STRONG_BAND), 'strong')).toBe(true); // both signs count
    expect(passesFilter(at(2), 'strong')).toBe(true);
    expect(passesFilter(at(STRONG_BAND - 0.01), 'strong')).toBe(false);
    expect(passesFilter(at(LEAN_BAND), 'strong')).toBe(false); // a lean is not strong
    expect(passesFilter(at(0), 'strong')).toBe(false);
  });
});

/* ----------------------------------------------------------------------- */
/* Pure helper: sortRows                                                   */
/* ----------------------------------------------------------------------- */

function row(over: Partial<ConsensusTableRow>): ConsensusTableRow {
  return {
    currency: 'USD',
    score: 0,
    scoreDelta: null,
    avg: null,
    vs: null,
    confidence: 0.5,
    agreement: 0.5,
    signal: 'Neutral',
    ...over,
  };
}

describe('sortRows', () => {
  it('sorts numerically descending on score', () => {
    const rows = [row({ currency: 'A', score: -1 }), row({ currency: 'B', score: 1.5 }), row({ currency: 'C', score: 0.2 })];
    const out = sortRows(rows, 'score', 'desc');
    expect(out.map((r) => r.currency)).toEqual(['B', 'C', 'A']);
  });

  it('sorts numerically ascending on score', () => {
    const rows = [row({ currency: 'A', score: -1 }), row({ currency: 'B', score: 1.5 }), row({ currency: 'C', score: 0.2 })];
    const out = sortRows(rows, 'score', 'asc');
    expect(out.map((r) => r.currency)).toEqual(['A', 'C', 'B']);
  });

  it('sorts the currency code lexically', () => {
    const rows = [row({ currency: 'JPY' }), row({ currency: 'AUD' }), row({ currency: 'EUR' })];
    expect(sortRows(rows, 'currency', 'asc').map((r) => r.currency)).toEqual(['AUD', 'EUR', 'JPY']);
    expect(sortRows(rows, 'currency', 'desc').map((r) => r.currency)).toEqual(['JPY', 'EUR', 'AUD']);
  });

  it('sorts the signal label lexically', () => {
    const rows = [
      row({ currency: 'A', signal: 'Strong bull' }),
      row({ currency: 'B', signal: 'Bearish lean' }),
      row({ currency: 'C', signal: 'Neutral' }),
    ];
    expect(sortRows(rows, 'signal', 'asc').map((r) => r.currency)).toEqual(['B', 'C', 'A']);
  });

  it('sorts on the windowed avg, ordering nulls last in both directions', () => {
    const rows = [
      row({ currency: 'A', avg: 0.5 }),
      row({ currency: 'B', avg: null }),
      row({ currency: 'C', avg: -0.5 }),
    ];
    expect(sortRows(rows, 'avg', 'desc').map((r) => r.currency)).toEqual(['A', 'C', 'B']);
    expect(sortRows(rows, 'avg', 'asc').map((r) => r.currency)).toEqual(['C', 'A', 'B']);
  });

  it('is stable for equal keys (preserves input order)', () => {
    const rows = [
      row({ currency: 'A', score: 1 }),
      row({ currency: 'B', score: 1 }),
      row({ currency: 'C', score: 1 }),
    ];
    expect(sortRows(rows, 'score', 'desc').map((r) => r.currency)).toEqual(['A', 'B', 'C']);
    expect(sortRows(rows, 'score', 'asc').map((r) => r.currency)).toEqual(['A', 'B', 'C']);
  });

  it('does not mutate the input array', () => {
    const rows = [row({ currency: 'A', score: 1 }), row({ currency: 'B', score: 2 })];
    const snapshot = rows.map((r) => r.currency);
    sortRows(rows, 'score', 'asc');
    expect(rows.map((r) => r.currency)).toEqual(snapshot);
  });
});

/* ----------------------------------------------------------------------- */
/* Component render                                                        */
/* ----------------------------------------------------------------------- */

describe('ConsensusDataTable render', () => {
  const series = tenCurrencySeries();
  const latest = latestFrom(series);

  it('renders every sortable column header', () => {
    const html = render(series, latest);
    for (const label of ['Ccy', 'Consensus', 'Δ prior', 'Avg', 'vs Avg', 'Conf', 'Agree', 'Signal']) {
      expect(html).toContain(label);
    }
  });

  it('renders one body row per G10 currency', () => {
    const html = render(series, latest);
    for (const ccy of G10_CURRENCIES) {
      expect(html).toContain(`>${ccy}<`);
    }
    const rowCount = (html.match(/data-ccy=/g) ?? []).length;
    expect(rowCount).toBe(G10_CURRENCIES.length);
  });

  it('renders the shared divergent score bar in each row', () => {
    const html = render(series, latest);
    expect(html).toContain('dbar-track');
    expect(html).toContain('dbar-fill');
  });

  it('renders all four filter chips', () => {
    const html = render(series, latest);
    for (const label of ['All', 'Bullish', 'Bearish', 'Strong']) {
      expect(html).toContain(label);
    }
  });

  // A discriminating latest-score mix so each filter narrows to a DISTINCT set,
  // exercising the bullish/bearish/strong band bounds through the rendered effect
  // (the SSR harness can't click, so initialFilter drives filter state).
  const filterLatest: FxConsensusSnapshotRow[] = [
    snap('USD', '2026-06-22', 1.3), // strong bull → bullish + strong
    snap('EUR', '2026-06-22', -1.3), // strong bear → bearish + strong
    snap('JPY', '2026-06-22', 0.5), // lean bull → bullish only
    snap('GBP', '2026-06-22', -0.5), // lean bear → bearish only
    snap('CHF', '2026-06-22', 0.1), // neutral → 'all' only
  ];

  it("initialFilter='all' renders every currency row", () => {
    const html = render(filterLatest, filterLatest, EMPTY_DELTAS, 'all');
    expect(renderedCcys(html).sort()).toEqual(['CHF', 'EUR', 'GBP', 'JPY', 'USD']);
  });

  it("initialFilter='bullish' keeps only scores at/above the lean band", () => {
    const html = render(filterLatest, filterLatest, EMPTY_DELTAS, 'bullish');
    // USD (+1.3) and JPY (+0.5) pass; EUR/GBP (negative) and CHF (+0.1) do not.
    expect(renderedCcys(html).sort()).toEqual(['JPY', 'USD']);
  });

  it("initialFilter='bearish' keeps only scores at/below the negative lean band", () => {
    const html = render(filterLatest, filterLatest, EMPTY_DELTAS, 'bearish');
    // EUR (-1.3) and GBP (-0.5) pass; USD/JPY (positive) and CHF (+0.1) do not.
    expect(renderedCcys(html).sort()).toEqual(['EUR', 'GBP']);
  });

  it("initialFilter='strong' keeps only either-sign strong-band convictions", () => {
    const html = render(filterLatest, filterLatest, EMPTY_DELTAS, 'strong');
    // USD (+1.3) and EUR (-1.3) clear |s|>=STRONG_BAND; the leans + neutral don't.
    expect(renderedCcys(html).sort()).toEqual(['EUR', 'USD']);
  });

  it('renders the averaging-window control with 3 / 5 / 10 / 20 options', () => {
    const html = render(series, latest);
    expect(html.toLowerCase()).toContain('window');
    for (const n of ['3', '5', '10', '20']) {
      expect(html).toContain(`data-n="${n}"`);
    }
    // Default window 5 is the pressed option.
    expect(html).toMatch(/data-n="5"[^>]*aria-pressed="true"/);
  });

  it('renders the default-window (5-run) Avg value for a currency', () => {
    const html = render(series, latest);
    // USD trailing-5 avg = (0.7+0.9+1.1+1.3) wait — USD scores ascend 0.3..1.3.
    // Trailing 5 of USD: (0.5+0.7+0.9+1.1+1.3)/5 = 0.90 → rendered as "0.90".
    expect(html).toContain('0.90');
  });

  it('shows a vs-Avg ▲ (above) and ▼ (below) inside the vs-Avg cell, not the sort header', () => {
    const html = render(series, latest);
    // The vs-Avg cells are the ONLY elements carrying this title; the sort-header
    // glyph (default score/desc → a ▼ on the Consensus header) lives elsewhere, so
    // matching the titled <td> content isolates the vs-Avg signal from the header.
    const vsCells = [...html.matchAll(/title="Latest score vs the windowed consensus average">([^<]*)</g)].map(
      (m) => m[1],
    );
    // One vs-Avg cell per rendered row.
    expect(vsCells).toHaveLength(G10_CURRENCIES.length);
    // USD latest 1.30 > trailing-5 avg 0.90 → above, gap +0.40.
    expect(vsCells).toContain('▲ +0.40');
    // EUR latest -1.30 < trailing-5 avg -0.90 → below, gap -0.40. This ▼ is the
    // genuine vs-Avg down-arrow, distinct from the desc sort-header indicator.
    expect(vsCells).toContain('▼ -0.40');
    // No vs-Avg cell should contain the OTHER currency's wrong-direction glyph by
    // accident: the down-arrow must come from a below-average cell, the up-arrow
    // from an above-average cell. (Regression-proofs the ▼ direction specifically.)
    expect(vsCells.some((c) => c.includes('▼'))).toBe(true);
    expect(vsCells.some((c) => c.includes('▲'))).toBe(true);
  });

  it('renders a friendly empty state with no data (no crash)', () => {
    const html = render([], []);
    expect(html.toLowerCase()).toContain('no consensus');
  });
});
