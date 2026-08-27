import { describe, expect, it } from 'vitest';
import {
  formatBriefWeightChange,
  isMaterialBookEvent,
  selectBriefBookEvent,
} from './brief-book-event';
import type { DashboardPositionEvent } from './types';

function ev(
  partial: Partial<DashboardPositionEvent> &
    Pick<DashboardPositionEvent, 'date' | 'ticker' | 'event'>
): DashboardPositionEvent {
  return {
    weight_pct: null,
    prev_weight_pct: null,
    weight_change_pct: null,
    price: null,
    thesis_id: null,
    reason: null,
    ...partial,
  };
}

describe('isMaterialBookEvent', () => {
  it('rejects HOLD and zero-display deltas', () => {
    expect(
      isMaterialBookEvent(
        ev({
          date: '2026-08-25',
          ticker: 'EWZ',
          event: 'HOLD',
          weight_pct: 10,
          prev_weight_pct: 10,
          weight_change_pct: 0,
        })
      )
    ).toBe(false);
    expect(
      isMaterialBookEvent(
        ev({
          date: '2026-08-25',
          ticker: 'EWZ',
          event: 'ADD',
          weight_pct: 10.04,
          prev_weight_pct: 10,
          weight_change_pct: 0.04,
        })
      )
    ).toBe(false);
  });

  it('accepts measurable ADD/TRIM and OPEN/EXIT', () => {
    expect(
      isMaterialBookEvent(
        ev({
          date: '2026-08-25',
          ticker: 'XLF',
          event: 'ADD',
          weight_pct: 15.2,
          prev_weight_pct: 15.1,
          weight_change_pct: 0.1,
        })
      )
    ).toBe(true);
    expect(
      isMaterialBookEvent(
        ev({ date: '2026-08-25', ticker: 'QQQ', event: 'OPEN', weight_pct: 8, prev_weight_pct: 0 })
      )
    ).toBe(true);
  });
});

describe('selectBriefBookEvent', () => {
  const derivedZero = ev({
    date: '2026-08-25',
    ticker: 'EWZ',
    event: 'ADD',
    weight_pct: 12.0,
    prev_weight_pct: 12.0,
    weight_change_pct: 0,
    reason:
      'Derived from positions book vs prior committed book 2026-08-24 (digest proposed_positions unavailable; no rebalance_decision.json for this date).',
  });

  const materialOlder = ev({
    date: '2026-08-20',
    ticker: 'XLF',
    event: 'TRIM',
    weight_pct: 14,
    prev_weight_pct: 16,
    weight_change_pct: -2,
    reason: 'Trim into stretched valuations.',
  });

  const materialSession = ev({
    date: '2026-08-27',
    ticker: 'VGK',
    event: 'ADD',
    weight_pct: 11.5,
    prev_weight_pct: 10,
    weight_change_pct: 1.5,
    reason: 'Add on improving international breadth.',
  });

  it('returns null when only derived zero-delta junk exists', () => {
    expect(selectBriefBookEvent([derivedZero], { sessionDate: '2026-08-27' })).toBeNull();
  });

  it('prefers a material move on the session date over an older move', () => {
    expect(
      selectBriefBookEvent([derivedZero, materialOlder, materialSession], {
        sessionDate: '2026-08-27',
      })
    ).toEqual(materialSession);
  });

  it('falls back to the latest material change when the session has none', () => {
    expect(
      selectBriefBookEvent([derivedZero, materialOlder], { sessionDate: '2026-08-27' })
    ).toEqual(materialOlder);
  });

  it('picks the largest move on a shared date', () => {
    const small = ev({
      date: '2026-08-27',
      ticker: 'AAA',
      event: 'ADD',
      weight_pct: 10.1,
      prev_weight_pct: 10,
      weight_change_pct: 0.1,
    });
    const large = ev({
      date: '2026-08-27',
      ticker: 'ZZZ',
      event: 'TRIM',
      weight_pct: 5,
      prev_weight_pct: 12,
      weight_change_pct: -7,
    });
    expect(selectBriefBookEvent([small, large], { sessionDate: '2026-08-27' })).toEqual(large);
  });
});

describe('formatBriefWeightChange', () => {
  it('omits 0.0pp display noise', () => {
    expect(
      formatBriefWeightChange(
        ev({
          date: '2026-08-25',
          ticker: 'EWZ',
          event: 'ADD',
          weight_pct: 10.04,
          prev_weight_pct: 10,
          weight_change_pct: 0.04,
        })
      )
    ).toBeNull();
    expect(
      formatBriefWeightChange(
        ev({
          date: '2026-08-25',
          ticker: 'XLF',
          event: 'ADD',
          weight_pct: 15.2,
          prev_weight_pct: 15.1,
          weight_change_pct: 0.1,
        })
      )
    ).toBe('+0.1pp');
  });
});
