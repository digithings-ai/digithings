import { describe, expect, it } from 'vitest';
import {
  formatBriefWeightChange,
  isMaterialBookEvent,
  selectBriefBookEvent,
  selectBriefLedgerDayEvents,
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

  it('treats a correctly projected +5pp ADD as material and a 0.0000 ADD as not', () => {
    expect(
      isMaterialBookEvent(
        ev({
          date: '2026-08-28',
          ticker: 'FXI',
          event: 'ADD',
          weight_pct: 15,
          prev_weight_pct: 10,
          weight_change_pct: 5,
        })
      )
    ).toBe(true);
    expect(
      isMaterialBookEvent(
        ev({
          date: '2026-08-28',
          ticker: 'FXI',
          event: 'ADD',
          weight_pct: 15,
          prev_weight_pct: 15,
          weight_change_pct: 0,
        })
      )
    ).toBe(false);
  });

  it('does not treat HOLD as material even when the consecutive-book delta is 5pp', () => {
    expect(
      isMaterialBookEvent(
        ev({
          date: '2026-08-28',
          ticker: 'FXI',
          event: 'HOLD',
          weight_pct: 15,
          prev_weight_pct: 10,
          weight_change_pct: 5,
        })
      )
    ).toBe(false);
  });
});

describe('selectBriefLedgerDayEvents', () => {
  const derivedZero = ev({
    date: '2026-08-27',
    ticker: 'EWZ',
    event: 'ADD',
    weight_pct: 12.0,
    prev_weight_pct: 12.0,
    weight_change_pct: 0,
  });

  const olderLarge = ev({
    date: '2026-08-25',
    ticker: 'VGK',
    event: 'TRIM',
    weight_pct: 10.1,
    prev_weight_pct: 20,
    weight_change_pct: -9.9,
  });

  const sessionTrim = ev({
    date: '2026-08-27',
    ticker: 'XLF',
    event: 'TRIM',
    weight_pct: 18,
    prev_weight_pct: 22,
    weight_change_pct: -4,
  });

  const sessionAdd = ev({
    date: '2026-08-27',
    ticker: 'EWJ',
    event: 'ADD',
    weight_pct: 11,
    prev_weight_pct: 10,
    weight_change_pct: 1,
  });

  it('returns only material moves on the session date, largest first', () => {
    expect(
      selectBriefLedgerDayEvents([derivedZero, olderLarge, sessionAdd, sessionTrim], '2026-08-27')
    ).toEqual([sessionTrim, sessionAdd]);
  });

  it('returns empty when the brief date has no material ledger rows (no older fallback)', () => {
    expect(selectBriefLedgerDayEvents([olderLarge, derivedZero], '2026-08-27')).toEqual([]);
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

  const largeStale = ev({
    date: '2026-08-25',
    ticker: 'VGK',
    event: 'TRIM',
    weight_pct: 10.1,
    prev_weight_pct: 20,
    weight_change_pct: -9.9,
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

  it('does not fall back to an older larger move when the session has none', () => {
    // Root cause of Brief Aug 25 VGK vs Aug 27 digest decision conflict:
    // session-scoped selection must not borrow the prior day's largest trim.
    expect(
      selectBriefBookEvent([derivedZero, largeStale], { sessionDate: '2026-08-27' })
    ).toBeNull();
  });

  it('without sessionDate, picks the latest material change date', () => {
    expect(selectBriefBookEvent([derivedZero, materialOlder, materialSession])).toEqual(
      materialSession
    );
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
