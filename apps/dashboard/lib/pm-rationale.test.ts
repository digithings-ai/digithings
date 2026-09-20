import { describe, expect, it } from 'vitest';
import {
  isDerivedBookReason,
  isMechanicalSizingRationale,
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

describe('resolvePmRationale', () => {
  it('prefers the first usable candidate and skips mechanical boilerplate', () => {
    expect(
      resolvePmRationale(
        'Position weight set by deterministic risk sizing.',
        'Financials still track the breadth recovery after the selloff.'
      )
    ).toBe('Financials still track the breadth recovery after the selloff.');
  });

  it('returns null when every candidate is boilerplate or blank', () => {
    expect(
      resolvePmRationale('Position weight set by deterministic risk sizing.', null)
    ).toBeNull();
  });

  it('keeps a real first rationale over a later one', () => {
    expect(resolvePmRationale('Valuation stretched into earnings.', 'Older narrative.')).toBe(
      'Valuation stretched into earnings.'
    );
  });
});
