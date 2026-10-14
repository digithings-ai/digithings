import { describe, expect, it } from 'vitest';
import { aggregateThesisWeightsByDate } from './queries';
import { thesisIdEquals } from './thesis-id';
import type { PositionHistoryRow } from './types';

describe('thesis-id matching', () => {
  it('compares thesis ids case-insensitively', () => {
    expect(thesisIdEquals('SHY', 'shy')).toBe(true);
    expect(thesisIdEquals(' shy ', 'SHY')).toBe(true);
  });

  it('aggregates position history independent of thesis id case', () => {
    const rows: PositionHistoryRow[] = [
      { date: '2026-06-17', ticker: 'SHY', weight_pct: 25, category: null, thesis_id: 'shy' },
      { date: '2026-06-17', ticker: 'BIL', weight_pct: 10, category: null, thesis_id: 'SHY' },
      { date: '2026-06-18', ticker: 'XLK', weight_pct: 15, category: null, thesis_id: 'growth' },
    ];

    expect(aggregateThesisWeightsByDate(rows, 'SHY')).toEqual([
      { date: '2026-06-17', weight_pct: 35 },
    ]);
  });
});

describe('thesis_id join normalization (F4)', () => {
  it('matches a lowercase position ticker to a vehicle- prefixed thesis id', () => {
    expect(thesisIdEquals('ewt', 'vehicle-ewt')).toBe(true);
    expect(thesisIdEquals('IJR', 'vehicle-ijr')).toBe(true);
  });
  it('still matches identical ids and rejects genuine mismatches', () => {
    expect(thesisIdEquals('MT1', 'MT1')).toBe(true);
    expect(thesisIdEquals('ewt', 'MT1')).toBe(false);
    expect(thesisIdEquals(null, 'MT1')).toBe(false);
  });
});
