import { describe, expect, it } from 'vitest';
import { normalizePositionEvent } from './position-events';

describe('normalizePositionEvent', () => {
  it('normalizes OPEN prior weight and delta from the current weight', () => {
    expect(
      normalizePositionEvent({
        date: '2026-06-18',
        ticker: 'XLK',
        event: 'OPEN',
        weight_pct: 12.5,
        prev_weight_pct: null,
        price: null,
        thesis_id: 'growth',
        reason: 'New sleeve',
      })
    ).toMatchObject({
      prev_weight_pct: 0,
      weight_change_pct: 12.5,
    });
  });

  it('preserves explicit prior weights for non-open events', () => {
    expect(
      normalizePositionEvent({
        date: '2026-06-18',
        ticker: 'SHY',
        event: 'ADD',
        weight_pct: '35',
        prev_weight_pct: '30',
        price: '82.5',
        thesis_id: null,
        reason: null,
      })
    ).toMatchObject({
      weight_pct: 35,
      prev_weight_pct: 30,
      weight_change_pct: 5,
      price: 82.5,
    });
  });
});
