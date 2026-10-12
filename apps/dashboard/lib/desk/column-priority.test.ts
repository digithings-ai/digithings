import { describe, expect, it } from 'vitest';
import { HOLDINGS_COLUMN_ORDER, HOLDINGS_MIN_WIDTH, visibleHoldingsColumns } from './column-priority';

describe('visibleHoldingsColumns', () => {
  it('drops Source, then Thesis, then Shares, then Value, then Name', () => {
    expect(visibleHoldingsColumns(HOLDINGS_MIN_WIDTH.Source)).toEqual([...HOLDINGS_COLUMN_ORDER]);
    expect(visibleHoldingsColumns(HOLDINGS_MIN_WIDTH.Source - 1)).not.toContain('Source');
    expect(visibleHoldingsColumns(HOLDINGS_MIN_WIDTH.Thesis - 1)).not.toContain('Thesis');
    expect(visibleHoldingsColumns(HOLDINGS_MIN_WIDTH.Shares - 1)).not.toContain('Shares');
    expect(visibleHoldingsColumns(HOLDINGS_MIN_WIDTH.Value - 1)).not.toContain('Value');
    expect(visibleHoldingsColumns(HOLDINGS_MIN_WIDTH.Name - 1)).toEqual(['Ticker', 'Weight', 'Day', 'Mark']);
  });
});
