/**
 * Ledger weight replay + reconciliation.
 *
 * The bug this pins (DIG-2803): the committed book carried weights written by
 * five writers that never checked `position_events`, so `/allocations` reported
 * UUP 29.9733 / DBO 4.7194 / XLV 5.0322 while the 25 Sep rebalance in the
 * ledger says 15 / 10 / 10. The tests below pin the replay rules and, above
 * all, the FAIL-CLOSED half: a ledger we cannot read must never move a weight.
 */
import { describe, expect, it } from 'vitest';

import {
  LEDGER_WEIGHT_EVENT_TYPES,
  reconcileWeightsAgainstLedger,
  replayLedgerWeights,
  type LedgerWeightEvent,
} from './ledger-weights';

function ev(
  date: string,
  ticker: string,
  event: string,
  weightPct: number | null,
  prevWeightPct: number | null = null,
): LedgerWeightEvent {
  return { date, ticker, event, weightPct, prevWeightPct };
}

// ---------------------------------------------------------------------------
// The four event types are a closed vocabulary; a typo must not open one.
// ---------------------------------------------------------------------------
describe('LEDGER_WEIGHT_EVENT_TYPES', () => {
  it('is exactly OPEN / ADD / EXIT / TRIM', () => {
    expect([...LEDGER_WEIGHT_EVENT_TYPES]).toEqual(['OPEN', 'ADD', 'EXIT', 'TRIM']);
  });
});

// ---------------------------------------------------------------------------
// replayLedgerWeights
// ---------------------------------------------------------------------------
describe('replayLedgerWeights', () => {
  it('replays the 25 Sep rebalance to 15 / 10 / 10 as of a 28 Sep book', () => {
    const state = replayLedgerWeights(
      [
        ev('2026-09-25', 'UUP', 'OPEN', 15, 10),
        ev('2026-09-25', 'DBO', 'OPEN', 10, 5),
        ev('2026-09-25', 'XLV', 'TRIM', 10, 15),
      ],
      '2026-09-28',
    );

    expect(state.targets.get('UUP')?.weightPct).toBe(15);
    expect(state.targets.get('DBO')?.weightPct).toBe(10);
    expect(state.targets.get('XLV')?.weightPct).toBe(10);
    expect(state.targets.get('UUP')?.event).toBe('OPEN');
    expect(state.targets.get('UUP')?.prevWeightPct).toBe(10);
    expect(state.applied).toBe(3);
    expect(state.latestEventDate).toBe('2026-09-25');
  });

  it('takes the latest decision per ticker when a day replays the rebalance', () => {
    // The 28 Sep replay carries the SAME targets as 25 Sep. Replaying as of a
    // 28 Sep book must not double-count it: one target per ticker, last wins.
    const state = replayLedgerWeights(
      [
        ev('2026-09-25', 'UUP', 'OPEN', 15, 10),
        ev('2026-09-25', 'DBO', 'OPEN', 10, 5),
        ev('2026-09-25', 'XLV', 'TRIM', 10, 15),
        ev('2026-09-28', 'UUP', 'OPEN', 15, 15),
        ev('2026-09-28', 'DBO', 'OPEN', 10, 10),
        ev('2026-09-28', 'XLV', 'TRIM', 10, 10),
      ],
      '2026-09-28',
    );

    expect(state.targets.size).toBe(3);
    expect(state.applied).toBe(6);
    expect(state.latestEventDate).toBe('2026-09-28');
    expect(state.targets.get('XLV')?.eventDate).toBe('2026-09-28');
  });

  it('ignores decisions dated after the committed book date', () => {
    const state = replayLedgerWeights(
      [ev('2026-09-25', 'UUP', 'OPEN', 15), ev('2026-10-01', 'UUP', 'TRIM', 1)],
      '2026-09-28',
    );

    expect(state.future).toBe(1);
    expect(state.targets.get('UUP')?.weightPct).toBe(15);
  });

  it('a null weight never zeroes a live position', () => {
    const state = replayLedgerWeights(
      [ev('2026-09-25', 'UUP', 'OPEN', 15), ev('2026-09-26', 'UUP', 'TRIM', null)],
      '2026-09-28',
    );

    expect(state.unusableWeight).toBe(1);
    expect(state.targets.get('UUP')?.weightPct).toBe(15);
    expect(state.targets.get('UUP')?.eventDate).toBe('2026-09-25');
  });

  it('rejects negative and non-finite weights the same way', () => {
    const state = replayLedgerWeights(
      [
        ev('2026-09-25', 'A', 'OPEN', 10),
        ev('2026-09-26', 'A', 'TRIM', -5),
        ev('2026-09-27', 'B', 'OPEN', Number.NaN),
        ev('2026-09-27', 'C', 'OPEN', Number.POSITIVE_INFINITY),
      ],
      '2026-09-28',
    );

    expect(state.unusableWeight).toBe(3);
    expect(state.targets.get('A')?.weightPct).toBe(10);
    expect(state.targets.has('B')).toBe(false);
    expect(state.targets.has('C')).toBe(false);
  });

  it('EXIT removes the target and re-OPEN restores it', () => {
    const state = replayLedgerWeights(
      [
        ev('2026-09-25', 'IJR', 'OPEN', 10),
        ev('2026-09-26', 'IJR', 'EXIT', null),
        ev('2026-09-27', 'IJR', 'OPEN', 7),
      ],
      '2026-09-28',
    );

    // The re-OPEN is the last event, so the target is restored and `exited` is cleared.
    expect(state.targets.has('IJR')).toBe(true);
    expect(state.targets.get('IJR')?.weightPct).toBe(7);
    expect(state.targets.get('IJR')?.event).toBe('OPEN');
    expect(state.targets.get('IJR')?.eventDate).toBe('2026-09-27');
    expect(state.exited.has('IJR')).toBe(false);
    expect(state.applied).toBe(3);
  });

  it('an EXIT with no later re-OPEN leaves the ticker exited and untargeted', () => {
    const state = replayLedgerWeights(
      [ev('2026-09-25', 'IJR', 'OPEN', 10), ev('2026-09-26', 'IJR', 'EXIT', null)],
      '2026-09-28',
    );

    expect(state.targets.has('IJR')).toBe(false);
    expect(state.exited.has('IJR')).toBe(true);
  });

  it('ignores unknown event types, malformed dates and blank tickers', () => {
    const state = replayLedgerWeights(
      [
        ev('2026-09-25', 'UUP', 'ROLL', 15),
        ev('2026-02-31', 'UUP', 'OPEN', 15),
        ev('not-a-date', 'UUP', 'OPEN', 15),
        ev('2026-09-25', '   ', 'OPEN', 15),
      ],
      '2026-09-28',
    );

    expect(state.ignored).toBe(4);
    expect(state.applied).toBe(0);
    expect(state.targets.size).toBe(0);
  });

  it('accepts lower-case and padded event spellings', () => {
    const state = replayLedgerWeights([ev('2026-09-25', 'UUP', ' open ', 15)], '2026-09-28');

    expect(state.targets.get('UUP')?.event).toBe('OPEN');
    expect(state.ignored).toBe(0);
  });

  it('is order-independent: caller ordering cannot change the outcome', () => {
    const forward = replayLedgerWeights(
      [ev('2026-09-25', 'UUP', 'OPEN', 10), ev('2026-09-27', 'UUP', 'TRIM', 15)],
      '2026-09-28',
    );
    const reversed = replayLedgerWeights(
      [ev('2026-09-27', 'UUP', 'TRIM', 15), ev('2026-09-25', 'UUP', 'OPEN', 10)],
      '2026-09-28',
    );

    expect(reversed.targets.get('UUP')).toEqual(forward.targets.get('UUP'));
    expect(reversed.latestEventDate).toBe(forward.latestEventDate);
  });

  it('returns an empty state when there is no usable book date', () => {
    for (const bookDate of [null, '', 'not-a-date', '2026-02-31']) {
      const state = replayLedgerWeights([ev('2026-09-25', 'UUP', 'OPEN', 15)], bookDate);

      expect(state.targets.size).toBe(0);
      expect(state.latestEventDate).toBeNull();
      expect(state.applied).toBe(0);
    }
  });
});

// ---------------------------------------------------------------------------
// reconcileWeightsAgainstLedger
// ---------------------------------------------------------------------------
describe('reconcileWeightsAgainstLedger', () => {
  const chrisBook = [
    { ticker: 'UUP', weightActual: 29.9733 },
    { ticker: 'DBO', weightActual: 4.7194 },
    { ticker: 'XLV', weightActual: 5.0322 },
  ];
  const chrisState = replayLedgerWeights(
    [
      ev('2026-09-25', 'UUP', 'OPEN', 15, 10),
      ev('2026-09-25', 'DBO', 'OPEN', 10, 5),
      ev('2026-09-25', 'XLV', 'TRIM', 10, 15),
    ],
    '2026-09-28',
  );

  it("DIG-2803: replaces the writers' book with the 25 Sep ledger targets", () => {
    const out = reconcileWeightsAgainstLedger(chrisBook, chrisState);

    expect(out.resolved.get('UUP')?.weightPct).toBe(15);
    expect(out.resolved.get('DBO')?.weightPct).toBe(10);
    expect(out.resolved.get('XLV')?.weightPct).toBe(10);
    expect(out.reconciledCount).toBe(3);
    expect(out.driftedCount).toBe(3);
    expect(out.unreconciled).toEqual([]);
    expect(out.conflicts).toEqual([]);
  });

  it("DIG-2803: keeps the positions value beside the ledger one (nothing hidden)", () => {
    const out = reconcileWeightsAgainstLedger(chrisBook, chrisState);

    expect(out.resolved.get('UUP')?.positionsWeightPct).toBe(29.9733);
    expect(out.resolved.get('UUP')?.driftPp).toBeCloseTo(14.9733, 6);
    expect(out.resolved.get('DBO')?.positionsWeightPct).toBe(4.7194);
    expect(out.resolved.get('DBO')?.driftPp).toBeCloseTo(-5.2806, 6);
    expect(out.resolved.get('XLV')?.positionsWeightPct).toBe(5.0322);
    expect(out.resolved.get('XLV')?.driftPp).toBeCloseTo(-4.9678, 6);
  });

  it('reports zero drift when the book already agrees with the ledger', () => {
    const state = replayLedgerWeights([ev('2026-09-25', 'UUP', 'OPEN', 15)], '2026-09-28');
    const out = reconcileWeightsAgainstLedger([{ ticker: 'UUP', weightActual: 15 }], state);

    expect(out.resolved.get('UUP')?.driftPp).toBe(0);
    expect(out.driftedCount).toBe(0);
    expect(out.reconciledCount).toBe(1);
  });

  it('FAIL CLOSED: a null state leaves every weight exactly as the book had it', () => {
    const out = reconcileWeightsAgainstLedger(chrisBook, null);

    for (const row of chrisBook) {
      const got = out.resolved.get(row.ticker);
      expect(got?.weightPct).toBe(row.weightActual);
      expect(got?.positionsWeightPct).toBe(row.weightActual);
      expect(got?.weightSource).toBe('positions');
      expect(got?.ledgerWeightPct).toBeNull();
      expect(got?.driftPp).toBeNull();
    }
    expect(out.reconciledCount).toBe(0);
    expect(out.driftedCount).toBe(0);
    expect(out.state).toBeNull();
  });

  it('FAIL CLOSED: an empty replay is not coverage either', () => {
    const state = replayLedgerWeights([], '2026-09-28');
    const out = reconcileWeightsAgainstLedger(chrisBook, state);

    expect(state.targets.size).toBe(0);
    expect(out.resolved.get('UUP')?.weightSource).toBe('positions');
    expect(out.reconciledCount).toBe(0);
  });

  it('CASH is never reconciled — it is not a ledger subject', () => {
    const state = replayLedgerWeights([ev('2026-09-25', 'UUP', 'OPEN', 15)], '2026-09-28');
    const out = reconcileWeightsAgainstLedger(
      [
        { ticker: 'UUP', weightActual: 15 },
        { ticker: 'CASH', weightActual: 60 },
        { ticker: ' cash ', weightActual: 1 },
      ],
      state,
    );

    expect(out.resolved.has('CASH')).toBe(false);
    expect(out.resolved.size).toBe(1);
  });

  it('skips blank tickers instead of inventing a row for them', () => {
    const out = reconcileWeightsAgainstLedger([{ ticker: '  ', weightActual: 5 }], null);

    expect(out.resolved.size).toBe(0);
  });

  it('an exited ticker still in the book is a conflict, not a silent pass', () => {
    const state = replayLedgerWeights(
      [
        ev('2026-09-25', 'UUP', 'OPEN', 15),
        ev('2026-09-25', 'IJR', 'OPEN', 10),
        ev('2026-09-26', 'IJR', 'EXIT', null),
      ],
      '2026-09-28',
    );
    const out = reconcileWeightsAgainstLedger(
      [
        { ticker: 'UUP', weightActual: 15 },
        { ticker: 'IJR', weightActual: 4 },
      ],
      state,
    );

    // IJR is the only anomaly here: UUP is covered and agrees, so `unreconciled`
    // is empty and UUP anchors to the ledger at zero drift.
    expect(out.conflicts).toEqual(['IJR']);
    expect(out.unreconciled).toEqual([]);
    expect(out.reconciledCount).toBe(1);
    expect(out.driftedCount).toBe(0);
    expect(out.resolved.get('IJR')?.weightSource).toBe('positions');
    expect(out.resolved.get('IJR')?.weightPct).toBe(4);
    expect(out.resolved.get('UUP')?.weightSource).toBe('ledger');
  });

  it('names a book holding the ledger never mentions', () => {
    const state = replayLedgerWeights([ev('2026-09-25', 'UUP', 'OPEN', 15)], '2026-09-28');
    const out = reconcileWeightsAgainstLedger(
      [
        { ticker: 'UUP', weightActual: 15 },
        { ticker: 'TLT', weightActual: 10 },
      ],
      state,
    );

    expect(out.unreconciled).toEqual(['TLT']);
    expect(out.resolved.get('TLT')?.weightSource).toBe('positions');
  });

  it('names a ledger target the book never carries', () => {
    const state = replayLedgerWeights(
      [
        ev('2026-09-25', 'UUP', 'OPEN', 15),
        ev('2026-09-25', 'GLD', 'OPEN', 10),
      ],
      '2026-09-28',
    );
    const out = reconcileWeightsAgainstLedger([{ ticker: 'UUP', weightActual: 15 }], state);

    expect(out.ledgerOnly).toEqual(['GLD']);
  });

  it('treats a null / non-finite book weight as zero, never as NaN', () => {
    const state = replayLedgerWeights([ev('2026-09-25', 'UUP', 'OPEN', 15)], '2026-09-28');
    const out = reconcileWeightsAgainstLedger(
      [
        { ticker: 'UUP', weightActual: null },
        { ticker: 'DBO', weightActual: Number.NaN },
      ],
      state,
    );

    expect(out.resolved.get('UUP')?.positionsWeightPct).toBe(0);
    expect(out.resolved.get('DBO')?.positionsWeightPct).toBe(0);
    expect(out.resolved.get('UUP')?.driftPp).toBe(-15);
    expect(out.resolved.get('DBO')?.weightSource).toBe('positions');
  });
});
