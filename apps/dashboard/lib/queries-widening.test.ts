import { describe, it, expect } from 'vitest';
import { mapThesisRow } from './queries';
import type { TableRow } from './database.types';

const row = (over: Partial<TableRow<'theses'>> = {}): TableRow<'theses'> => ({
  id: 'u', date: '2026-06-23', thesis_id: 'MT1', name: 'Small caps', vehicle: null,
  invalidation: null, status: 'ACTIVE', notes: null,
  ...over,
});

describe('mapThesisRow (F1)', () => {
  it('lifts confidence/horizon/kind/criteria/linked id', () => {
    const t = mapThesisRow(row({
      confidence: 0.72, horizon: '3-6mo', thesis_kind: 'market',
      validation_criteria: ['breadth widens', 'rates ease'] as unknown as TableRow<'theses'>['validation_criteria'],
      invalidation_criteria: ['credit blows out'] as unknown as TableRow<'theses'>['invalidation_criteria'],
      linked_market_thesis_id: null,
    }));
    expect(t.confidence).toBe(0.72);
    expect(t.horizon).toBe('3-6mo');
    expect(t.thesis_kind).toBe('market');
    expect(t.validation_criteria).toEqual(['breadth widens', 'rates ease']);
    expect(t.invalidation_criteria).toEqual(['credit blows out']);
  });
  it('coerces missing/non-array jsonb criteria to []', () => {
    const t = mapThesisRow(row());
    expect(t.validation_criteria).toEqual([]);
    expect(t.invalidation_criteria).toEqual([]);
    expect(t.confidence).toBeNull();
  });
});
