import { describe, expect, it } from 'vitest';
import { activeRebalanceActions } from './brief-highlight';
import type { RebalanceAction } from '@/lib/types';

describe('activeRebalanceActions', () => {
  it('drops HOLD and zero-weight EXIT no-ops', () => {
    const actions: RebalanceAction[] = [
      { ticker: 'SPY', current_pct: 50, recommended_pct: 50, action: 'HOLD' },
      { ticker: 'QQQ', current_pct: 0, recommended_pct: 0, action: 'EXIT' },
      { ticker: 'NVDA', current_pct: 8, recommended_pct: 6, action: 'TRIM' },
    ];
    expect(activeRebalanceActions(actions).map((a) => a.ticker)).toEqual(['NVDA']);
  });

  it('drops zero-pp ADD/TRIM noise (#3080)', () => {
    const actions: RebalanceAction[] = [
      { ticker: 'XLF', current_pct: 15.14, recommended_pct: 15.16, action: 'ADD' },
      { ticker: 'SPY', current_pct: 50, recommended_pct: 50, action: 'HOLD' },
    ];
    expect(activeRebalanceActions(actions)).toEqual([]);
  });
});
