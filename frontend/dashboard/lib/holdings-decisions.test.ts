import { describe, it, expect } from 'vitest';
import { latestDecisionByTicker, proposedNotHeld, decisionNodeFor } from './holdings-decisions';

const d = (over: Partial<{ ticker: string; run_date: string; stance: string; conviction: number | null; status: string }>) =>
  ({
    id: '1', run_id: 'r', ticker: 'X', run_date: '2026-06-23', stance: 'buy', conviction: 3,
    status: 'pending', thesis: null, benchmark: 'SPY', holding_days: 30, actual_return: null,
    alpha: null, reflection: null, resolved_at: null, created_at: null, ...over,
  });

describe('holdings-decisions', () => {
  it('keeps only the most recent decision per ticker', () => {
    const m = latestDecisionByTicker([
      d({ ticker: 'NVDA', run_date: '2026-06-20', conviction: 1 }),
      d({ ticker: 'NVDA', run_date: '2026-06-23', conviction: 4 }),
    ] as never);
    expect(m.get('NVDA')?.conviction).toBe(4);
  });

  it('returns decision tickers not in the held set, latest-first by run_date', () => {
    const out = proposedNotHeld(
      [
        d({ ticker: 'IWM', run_date: '2026-06-23', conviction: 2 }),
        d({ ticker: 'NVDA', run_date: '2026-06-23', conviction: 4 }),
      ] as never,
      new Set(['NVDA'])
    );
    expect(out.map((p) => p.ticker)).toEqual(['IWM']);
  });

  it('builds an analyst node key for the Pipeline deep-link', () => {
    expect(decisionNodeFor('qqq')).toBe('analyst/QQQ');
  });
});
