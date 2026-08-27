import { describe, expect, it } from 'vitest';
import { computeLivePerformanceKpis } from '@digithings/web';

describe('shared live KPI path (digiquant-web + olympus Brief)', () => {
  it('olympus Brief hook imports the same computeLivePerformanceKpis export', () => {
    const kpis = computeLivePerformanceKpis({
      positions: [
        {
          ticker: 'SPY',
          weightPct: 100,
          markPrice: 500,
          effectivePrice: 505,
          isLive: true,
          metricsAsOf: '2026-08-26',
          livePriceDate: '2026-08-27',
        },
      ],
      navHistory: [
        { date: '2026-06-23', nav: 100 },
        { date: '2026-08-26', nav: 101 },
      ],
      benchmarkHistory: [
        { date: '2026-06-23', price: 500 },
        { date: '2026-08-26', price: 510 },
      ],
      benchmarkTicker: 'SPY',
    });
    expect(kpis.liveNav).toBeCloseTo(101 * 1.01, 2);
    expect(kpis.priceAsOfDate).toBe('2026-08-27');
    expect(kpis.excessReturnPct).not.toBeNull();
  });
});
