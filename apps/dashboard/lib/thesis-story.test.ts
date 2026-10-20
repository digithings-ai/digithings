import { describe, expect, it } from 'vitest';
import {
  buildThesisStory,
  attributeWeightToPrimaryThesis,
  selectThesisAsOf,
  DEMO_THESIS_ANCHOR_DATE,
  type ThesisVehicleRow,
} from './thesis-story';
import { latestDecisionByTicker, type DecisionLogRow } from './holdings-decisions';
import type { Position, Thesis } from './types';

function thesis(p: Partial<Thesis>): Thesis {
  return {
    id: 'X', name: 'X', vehicle: null, invalidation: null, status: 'ACTIVE', notes: null,
    confidence: null, horizon: null, thesis_kind: 'market',
    validation_criteria: [], invalidation_criteria: [], linked_market_thesis_id: null,
    ...p,
  };
}

function position(p: Partial<Position>): Position {
  return {
    ticker: 'AAA', name: 'AAA', type: 'LONG', weight_actual: 10, current_price: 100,
    entry_price: 90, entry_date: null, rationale: '', thesis_ids: [], category: 'equity',
    pm_notes: '', stats: {}, ...p,
  };
}

function tv(p: Partial<ThesisVehicleRow>): ThesisVehicleRow {
  return { date: '2026-07-17', thesisId: 'MT1', ticker: 'AAA', rationale: null, candidateRank: 1, ...p };
}

function decision(p: Partial<DecisionLogRow>): DecisionLogRow {
  return {
    id: 'd', run_id: 'r', run_date: '2026-06-26', ticker: 'AAA', stance: 'buy', conviction: 3,
    thesis: null, benchmark: 'SPY', holding_days: 5, status: 'resolved', actual_return: 0.01,
    alpha: 0.001, reflection: null, resolved_at: null, created_at: null, ...p,
  };
}

describe('selectThesisAsOf', () => {
  const rows: ThesisVehicleRow[] = [
    tv({ date: '2026-07-17', thesisId: 'T1', ticker: 'BBB', candidateRank: 2 }),
    tv({ date: '2026-07-17', thesisId: 'T1', ticker: 'AAA', candidateRank: 1 }),
    tv({ date: '2026-07-12', thesisId: 'T1', ticker: 'CCC', candidateRank: 1 }),
    tv({ date: '2026-07-10', thesisId: 'T1', ticker: 'DDD', candidateRank: 1 }),
    tv({ date: '2026-07-17', thesisId: 'OTHER', ticker: 'ZZZ', candidateRank: 1 }),
  ];

  it('picks the overall latest date and orders by rank when no anchor', () => {
    const { rows: sel, asOf } = selectThesisAsOf(rows, 'T1', null);
    expect(asOf).toBe('2026-07-17');
    expect(sel.map((r) => r.ticker)).toEqual(['AAA', 'BBB']); // rank 1 before rank 2
  });

  it('caps at the anchor date (latest ≤ anchor)', () => {
    const { rows: sel, asOf } = selectThesisAsOf(rows, 'T1', '2026-07-12');
    expect(asOf).toBe('2026-07-12');
    expect(sel.map((r) => r.ticker)).toEqual(['CCC']);
  });

  it('treats the anchor as a soft ceiling (falls back to overall latest when all rows post-date it)', () => {
    const { asOf } = selectThesisAsOf(rows, 'T1', '2026-07-01');
    expect(asOf).toBe('2026-07-17');
  });

  it('returns empty for an unmapped thesis', () => {
    expect(selectThesisAsOf(rows, 'MISSING', null)).toEqual({ rows: [], asOf: null });
  });
});

describe('attributeWeightToPrimaryThesis', () => {
  it('attributes a many-to-many ticker to its lowest-rank thesis only (no double-count)', () => {
    const positions = [position({ ticker: 'CPER', weight_actual: 10 })];
    const rows = [
      tv({ thesisId: 'inflation', ticker: 'CPER', candidateRank: 1 }),
      tv({ thesisId: 'growth', ticker: 'CPER', candidateRank: 2 }),
    ];
    const w = attributeWeightToPrimaryThesis(positions, rows);
    expect(w.get('INFLATION')).toBeCloseTo(10, 5);
    expect(w.has('GROWTH')).toBe(false);
    // The whole book (10) is attributed exactly once.
    expect([...w.values()].reduce((s, x) => s + x, 0)).toBeCloseTo(10, 5);
  });

  it('breaks candidate_rank ties by lexical thesis_id', () => {
    const positions = [position({ ticker: 'XLB', weight_actual: 8 })];
    const rows = [
      tv({ thesisId: 'zeta', ticker: 'XLB', candidateRank: 1 }),
      tv({ thesisId: 'alpha', ticker: 'XLB', candidateRank: 1 }),
    ];
    const w = attributeWeightToPrimaryThesis(positions, rows);
    expect(w.get('ALPHA')).toBeCloseTo(8, 5);
    expect(w.has('ZETA')).toBe(false);
  });

  it('ignores mappings for tickers the book does not hold', () => {
    const positions = [position({ ticker: 'AAA', weight_actual: 5 })];
    const rows = [tv({ thesisId: 'MT1', ticker: 'BBB', candidateRank: 1 })];
    expect(attributeWeightToPrimaryThesis(positions, rows).size).toBe(0);
  });
});

describe('buildThesisStory', () => {
  const market = [
    thesis({ id: 'MT1', name: 'AI capex', confidence: 0.9 }),
    thesis({ id: 'MT2', name: 'EM rotation', confidence: 0.5 }),
  ];
  const positions = [
    position({ ticker: 'AAA', weight_actual: 20 }),
    position({ ticker: 'CCC', weight_actual: 15 }),
    position({ ticker: 'CASH', weight_actual: 5 }),
  ];
  const rows: ThesisVehicleRow[] = [
    tv({ thesisId: 'MT1', ticker: 'AAA', candidateRank: 1, rationale: 'AAA tracks AI capex' }),
    tv({ thesisId: 'MT2', ticker: 'AAA', candidateRank: 2, rationale: null }),
    tv({ thesisId: 'MT2', ticker: 'BBB', candidateRank: 1, rationale: null }),
  ];
  const decisionsByTicker = latestDecisionByTicker([
    decision({ ticker: 'AAA', conviction: -2, run_date: '2026-06-26', stance: 'sell' }),
  ]);

  const result = buildThesisStory(market, rows, positions, decisionsByTicker, {
    anchorDate: null,
    vehicleTheses: [thesis({ id: 'vehicle-BBB', thesis_kind: 'vehicle', notes: 'fallback note' })],
  });

  it('orders stories by confidence desc', () => {
    expect(result.stories.map((s) => s.thesis.id)).toEqual(['MT1', 'MT2']);
  });

  it('shows a many-to-many ticker under every thesis that maps it', () => {
    const mt1 = result.stories.find((s) => s.thesis.id === 'MT1')!;
    const mt2 = result.stories.find((s) => s.thesis.id === 'MT2')!;
    expect(mt1.vehicles.map((v) => v.ticker)).toContain('AAA');
    expect(mt2.vehicles.map((v) => v.ticker)).toContain('AAA');
  });

  it('joins held position + latest signed decision to a vehicle', () => {
    const aaa = result.stories[0].vehicles.find((v) => v.ticker === 'AAA')!;
    expect(aaa.position?.weight_actual).toBe(20);
    expect(aaa.latestDecision?.conviction).toBe(-2);
  });

  it('falls back to the vehicle thesis notes when thesis_vehicles.rationale is null', () => {
    const bbb = result.stories.find((s) => s.thesis.id === 'MT2')!.vehicles.find((v) => v.ticker === 'BBB')!;
    expect(bbb.rationale).toBe('fallback note');
  });

  it('puts held-but-not-shown tickers in heldUnmapped (excluding CASH)', () => {
    expect(result.unassigned.heldUnmapped.map((p) => p.ticker)).toEqual(['CCC']);
  });

  it('puts shown-but-unheld vehicles in proposedUnheld', () => {
    expect(result.unassigned.proposedUnheld.map((d) => d.ticker)).toEqual(['BBB']);
  });
});

describe('DEMO_THESIS_ANCHOR_DATE', () => {
  it('is the dense demo date', () => {
    expect(DEMO_THESIS_ANCHOR_DATE).toBe('2026-07-12');
  });
});
