import { describe, expect, it } from 'vitest';
import { aggregateThesisWeightsByDate } from './queries';
import { thesisPipelineNarrativeFromPayloads } from './thesis-pipeline-snapshot';
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

  it('matches pipeline narratives independent of thesis id case', () => {
    const result = thesisPipelineNarrativeFromPayloads(
      'SHY',
      { body: { theses: [{ thesis_id: 'shy', title: 'Defense', statement: 'Own duration.' }] } },
      { body: { mappings: [{ thesis_id: 'sHy', rationale: 'Use SHY.', candidate_tickers: ['SHY'] }] } }
    );

    expect(result.exploration).toContain('Defense');
    expect(result.vehicles).toContain('Use SHY.');
  });
});
