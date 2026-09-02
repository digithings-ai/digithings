import { describe, expect, it } from 'vitest';
import { buildRebalanceActions, isMaterialRebalanceAction } from './rebalance-actions';

/**
 * #1850 — position-size changes rendered "0.0% → 0.0%" on the dashboard.
 *
 * The fixtures below are the REAL 2026-08-04 production payload and book weights, because the
 * bug was invisible to any invented fixture that happened to include a `current_pct` key.
 */
describe('isMaterialRebalanceAction', () => {
  it('collapses ADD/TRIM that round to 0.0pp at desk precision (#3080)', () => {
    expect(
      isMaterialRebalanceAction({
        ticker: 'XLF',
        current_pct: 15.14,
        recommended_pct: 15.16,
        action: 'ADD',
      }),
    ).toBe(false);
    expect(
      isMaterialRebalanceAction({
        ticker: 'XLV',
        current_pct: 9.86,
        recommended_pct: 9.861,
        action: 'TRIM',
      }),
    ).toBe(false);
  });

  it('keeps material moves and genuine opens', () => {
    expect(
      isMaterialRebalanceAction({
        ticker: 'NVDA',
        current_pct: 8,
        recommended_pct: 6,
        action: 'TRIM',
      }),
    ).toBe(true);
    expect(
      isMaterialRebalanceAction({
        ticker: 'IJR',
        current_pct: 0,
        recommended_pct: 6,
        action: 'OPEN',
      }),
    ).toBe(true);
  });
});

describe('buildRebalanceActions', () => {
  // Exactly the shape the live pm-rebalance document carries: no current_pct anywhere.
  const LIVE_ACTIONS = [
    { action: 'trim', ticker: 'XLV', rationale: 'Position weight set by deterministic risk sizing.', target_pct: 5.0 },
    { action: 'add', ticker: 'XRT', rationale: 'Position weight set by deterministic risk sizing.', target_pct: 10.0 },
    { action: 'hold', ticker: 'VGK', rationale: '…', target_pct: 14.872 },
  ];
  // Prior book date (2026-08-03) weights, from prod.
  const PREV = new Map<string, number>([
    ['XLV', 9.8616],
    ['XRT', 4.9207],
    ['VGK', 14.872],
  ]);

  it('reads the prior weight from the previous book date', () => {
    const [xlv, xrt] = buildRebalanceActions(LIVE_ACTIONS, PREV);
    // The bug: both of these were 0.
    expect(xlv.current_pct).toBeCloseTo(9.8616, 4);
    expect(xrt.current_pct).toBeCloseTo(4.9207, 4);
  });

  it('maps target_pct to the recommended weight', () => {
    const [xlv, xrt] = buildRebalanceActions(LIVE_ACTIONS, PREV);
    expect(xlv.recommended_pct).toBe(5.0);
    expect(xrt.recommended_pct).toBe(10.0);
  });

  it('produces a trim that reads as a decrease and an add as an increase', () => {
    const [xlv, xrt] = buildRebalanceActions(LIVE_ACTIONS, PREV);
    expect(xlv.recommended_pct - xlv.current_pct).toBeLessThan(0); // 9.86 → 5.0
    expect(xrt.recommended_pct - xrt.current_pct).toBeGreaterThan(0); // 4.92 → 10.0
  });

  it('does not confuse a hold with a change', () => {
    const [, , vgk] = buildRebalanceActions(LIVE_ACTIONS, PREV);
    expect(vgk.current_pct).toBeCloseTo(vgk.recommended_pct, 6);
  });

  it('treats an absent prior weight as genuinely not held', () => {
    // A brand-new position has no prior-date row. 0% is a real value here, not a fabrication —
    // it is an OPEN, and the delta from 0 is the whole position.
    const [row] = buildRebalanceActions([{ action: 'new', ticker: 'IJR', target_pct: 6 }], PREV);
    expect(row.current_pct).toBe(0);
    expect(row.recommended_pct).toBe(6);
  });

  it('prefers an explicit current_pct when the payload ever starts carrying one', () => {
    const [row] = buildRebalanceActions(
      [{ action: 'trim', ticker: 'XLV', current_pct: 30, target_pct: 15 }],
      PREV,
    );
    expect(row.current_pct).toBe(30); // not 9.8616
  });

  it('normalises the ticker before looking up the prior weight', () => {
    const [row] = buildRebalanceActions([{ action: 'trim', ticker: ' xlv ', target_pct: 5 }], PREV);
    expect(row.ticker).toBe('XLV');
    expect(row.current_pct).toBeCloseTo(9.8616, 4);
  });

  it('uppercases the action and defaults it to HOLD', () => {
    const rows = buildRebalanceActions(
      [{ ticker: 'XLV', target_pct: 5 }, { action: 'exit', ticker: 'XRT', target_pct: 0 }],
      PREV,
    );
    expect(rows[0].action).toBe('HOLD');
    expect(rows[1].action).toBe('EXIT');
  });

  it('skips junk entries rather than emitting a nameless row', () => {
    expect(
      buildRebalanceActions([null, 'nope', {}, { ticker: '   ' }, { ticker: 'XLV', target_pct: 5 }], PREV),
    ).toHaveLength(1);
  });

  it('returns an empty list for a non-array payload', () => {
    for (const bad of [null, undefined, {}, 'actions', 42]) {
      expect(buildRebalanceActions(bad, PREV)).toEqual([]);
    }
  });

  it('omits rationale when the payload has none', () => {
    const [row] = buildRebalanceActions([{ action: 'trim', ticker: 'XLV', target_pct: 5 }], PREV);
    expect('rationale' in row).toBe(false);
  });
});
