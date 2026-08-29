import { describe, expect, it } from 'vitest';
import {
  isActiveRebalanceAction,
  isMaterialRebalanceDelta,
} from './rebalance-materiality';

describe('rebalance-materiality', () => {
  it('treats rounded 0.0pp ADD/TRIM as immaterial', () => {
    expect(
      isMaterialRebalanceDelta({
        ticker: 'SPY',
        current_pct: 10.04,
        recommended_pct: 10.01,
        action: 'TRIM',
      }),
    ).toBe(false);
    expect(
      isActiveRebalanceAction({
        ticker: 'SPY',
        current_pct: 10.04,
        recommended_pct: 10.01,
        action: 'TRIM',
      }),
    ).toBe(false);
  });

  it('keeps material trims and opens', () => {
    expect(
      isActiveRebalanceAction({
        ticker: 'NVDA',
        current_pct: 8,
        recommended_pct: 6,
        action: 'TRIM',
      }),
    ).toBe(true);
    expect(
      isActiveRebalanceAction({
        ticker: 'IWM',
        current_pct: 0,
        recommended_pct: 5,
        action: 'OPEN',
      }),
    ).toBe(true);
  });
});
