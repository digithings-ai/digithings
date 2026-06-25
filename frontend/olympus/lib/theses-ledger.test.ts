import { describe, expect, it } from 'vitest';
import { splitTheses, sortByConfidenceDesc, groupVehicleTheses, findThesisById } from './theses-ledger';
import { aggregateWeightByThesis, bookWeightForThesis } from './portfolio-aggregates';
import type { Thesis } from './types';

function mk(p: Partial<Thesis>): Thesis {
  return {
    id: 'X', name: 'X', vehicle: null, invalidation: null, status: 'ACTIVE', notes: null,
    confidence: null, horizon: null, thesis_kind: null,
    validation_criteria: [], invalidation_criteria: [], linked_market_thesis_id: null,
    ...p,
  };
}

describe('splitTheses', () => {
  it('routes vehicle kind to vehicle, everything else to market', () => {
    const out = splitTheses([
      mk({ id: 'MT1', thesis_kind: 'market' }),
      mk({ id: 'vehicle-ewt', thesis_kind: 'vehicle' }),
      mk({ id: 'LEGACY', thesis_kind: null }),
    ]);
    expect(out.market.map((t) => t.id)).toEqual(['MT1', 'LEGACY']);
    expect(out.vehicle.map((t) => t.id)).toEqual(['vehicle-ewt']);
  });
});

describe('sortByConfidenceDesc', () => {
  it('orders by confidence desc, nulls last, stable by name', () => {
    const out = sortByConfidenceDesc([
      mk({ id: 'a', name: 'Apple', confidence: 0.4 }),
      mk({ id: 'b', name: 'Beta', confidence: null }),
      mk({ id: 'c', name: 'Cobalt', confidence: 0.9 }),
      mk({ id: 'd', name: 'Delta', confidence: null }),
    ]);
    expect(out.map((t) => t.id)).toEqual(['c', 'a', 'b', 'd']);
  });
});

describe('groupVehicleTheses', () => {
  const market = [
    mk({ id: 'MT1', name: 'AI capex', confidence: 0.9 }),
    mk({ id: 'MT2', name: 'EM rotation', confidence: 0.5 }),
  ];
  it('groups vehicles under their linked market thesis, parents sorted by confidence desc', () => {
    const vehicle = [
      mk({ id: 'vehicle-ewt', thesis_kind: 'vehicle', linked_market_thesis_id: 'MT2' }),
      mk({ id: 'vehicle-nvda', thesis_kind: 'vehicle', linked_market_thesis_id: 'MT1' }),
    ];
    const groups = groupVehicleTheses(vehicle, market);
    expect(groups.map((g) => g.marketId)).toEqual(['MT1', 'MT2']);
    expect(groups[0].marketName).toBe('AI capex');
    expect(groups[0].theses.map((t) => t.id)).toEqual(['vehicle-nvda']);
  });
  it('places unmatched and null-link vehicles in a trailing unlinked group', () => {
    const vehicle = [
      mk({ id: 'vehicle-ijr', thesis_kind: 'vehicle', linked_market_thesis_id: null }),
      mk({ id: 'vehicle-gone', thesis_kind: 'vehicle', linked_market_thesis_id: 'MISSING' }),
      mk({ id: 'vehicle-nvda', thesis_kind: 'vehicle', linked_market_thesis_id: 'MT1' }),
    ];
    const groups = groupVehicleTheses(vehicle, market);
    const last = groups[groups.length - 1];
    expect(last.marketId).toBeNull();
    expect(last.theses.map((t) => t.id).sort()).toEqual(['vehicle-gone', 'vehicle-ijr']);
  });
});

describe('findThesisById', () => {
  it('matches via normalized thesis-id equality (vehicle- prefix tolerant)', () => {
    const found = findThesisById([mk({ id: 'vehicle-ewt', name: 'EWT' })], 'ewt');
    expect(found?.id).toBe('vehicle-ewt');
  });
});

describe('bookWeightForThesis', () => {
  const all = [
    mk({ id: 'MT1', thesis_kind: 'market' }),
    mk({ id: 'vehicle-nvda', thesis_kind: 'vehicle', linked_market_thesis_id: 'MT1' }),
    mk({ id: 'vehicle-ewt', thesis_kind: 'vehicle', linked_market_thesis_id: null }),
  ];
  const weightByThesisId = aggregateWeightByThesis([
    { weight_actual: 30, thesis_ids: ['vehicle-nvda'] },
    { weight_actual: 12, thesis_ids: ['vehicle-ewt'] },
    { weight_actual: 8, thesis_ids: ['MT1'] },
  ]);

  it('a vehicle thesis reports its own bucket weight', () => {
    const v = all.find((t) => t.id === 'vehicle-nvda')!;
    expect(bookWeightForThesis(v, weightByThesisId, all)).toBeCloseTo(30, 5);
  });

  it('a market thesis rolls up its own weight plus its linked vehicles', () => {
    const m = all.find((t) => t.id === 'MT1')!;
    // MT1 direct 8 + vehicle-nvda 30 = 38
    expect(bookWeightForThesis(m, weightByThesisId, all)).toBeCloseTo(38, 5);
  });
});
