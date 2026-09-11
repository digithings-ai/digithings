import { describe, expect, it } from 'vitest';
import {
  buildDisplayRationaleByTicker,
  isDerivedBookReason,
  isMechanicalSizingRationale,
  narrativesFromPmDirectionMemo,
  resolvePmRationale,
  usablePmRationale,
} from './pm-rationale';

describe('isMechanicalSizingRationale', () => {
  it('treats the canonical H8 fallback as empty', () => {
    expect(isMechanicalSizingRationale('Position weight set by deterministic risk sizing.')).toBe(
      true
    );
    expect(isMechanicalSizingRationale('position weight set by deterministic risk sizing')).toBe(
      true
    );
    expect(isMechanicalSizingRationale('  Weight set by deterministic risk sizing.  ')).toBe(true);
  });

  it('keeps real PM thesis text', () => {
    expect(
      isMechanicalSizingRationale('Trim into stretched valuations ahead of earnings.')
    ).toBe(false);
    expect(usablePmRationale('Trim into stretched valuations ahead of earnings.')).toBe(
      'Trim into stretched valuations ahead of earnings.'
    );
  });

  it('treats blank as non-display', () => {
    expect(isMechanicalSizingRationale('')).toBe(true);
    expect(isMechanicalSizingRationale(null)).toBe(true);
    expect(usablePmRationale('   ')).toBeNull();
  });
});

describe('isDerivedBookReason', () => {
  it('hides execute_at_open derived fallback prose from desk UI', () => {
    const reason =
      'Derived from positions book vs prior committed book 2026-08-24 (digest proposed_positions unavailable; no rebalance_decision.json for this date).';
    expect(isDerivedBookReason(reason)).toBe(true);
    expect(usablePmRationale(reason)).toBeNull();
  });

  it('keeps real PM thesis text', () => {
    expect(isDerivedBookReason('Maintain financial exposure while breadth confirms.')).toBe(false);
  });
});

describe('resolvePmRationale / buildDisplayRationaleByTicker', () => {
  it('skips mechanical rebalance text and prefers H7 roster narrative', () => {
    const map = buildDisplayRationaleByTicker({
      pmRebalanceActions: [
        {
          ticker: 'XLF',
          action: 'trim',
          rationale: 'Position weight set by deterministic risk sizing.',
        },
      ],
      pmDirectionMemo: {
        roster: [
          {
            ticker: 'XLF',
            direction: 'long',
            conviction_rank: 2,
            narrative: 'Financials still track the breadth recovery after the selloff.',
          },
        ],
      },
    });
    expect(map.XLF).toBe('Financials still track the breadth recovery after the selloff.');
  });

  it('omits tickers that only have the sizing boilerplate', () => {
    const map = buildDisplayRationaleByTicker({
      pmRebalanceActions: [
        {
          ticker: 'XLF',
          rationale: 'Position weight set by deterministic risk sizing.',
        },
      ],
    });
    expect(map).toEqual({});
    expect(
      resolvePmRationale('Position weight set by deterministic risk sizing.', null)
    ).toBeNull();
  });

  it('keeps a real pm-rebalance rationale over H7 when both exist', () => {
    const map = buildDisplayRationaleByTicker({
      pmRebalanceActions: [{ ticker: 'NVDA', rationale: 'Valuation stretched into earnings.' }],
      pmDirectionMemo: {
        roster: [{ ticker: 'NVDA', narrative: 'Older H7 narrative for NVDA.' }],
      },
    });
    expect(map.NVDA).toBe('Valuation stretched into earnings.');
  });

  it('extracts H7 narratives and ignores blank rows', () => {
    expect(
      narrativesFromPmDirectionMemo({
        roster: [
          { ticker: 'SPY', narrative: 'Core beta while breadth confirms.' },
          { ticker: 'cash', narrative: '' },
          { ticker: 'QQQ', narrative: 'Position weight set by deterministic risk sizing.' },
        ],
      })
    ).toEqual({ SPY: 'Core beta while breadth confirms.' });
  });
});
