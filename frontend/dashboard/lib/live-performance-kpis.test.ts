import { describe, expect, it } from 'vitest';
import { computeLivePerformanceKpis, MIN_OVERLAP_DAYS } from '@digithings/web';

describe('shared live KPI path (digiquant-web + dashboard Brief)', () => {
  it('dashboard Brief hook imports the same computeLivePerformanceKpis export', () => {
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

  it('yields non-null excess and alpha for Brief when NAV + SPY overlap ≥ MIN_OVERLAP_DAYS', () => {
    const navHistory: Array<{ date: string; nav: number }> = [];
    const benchmarkHistory: Array<{ date: string; price: number }> = [];
    let nav = 100;
    let price = 500;
    const start = Date.UTC(2026, 5, 2);
    for (let i = 0; navHistory.length < MIN_OVERLAP_DAYS + 3; i++) {
      const d = new Date(start + i * 86_400_000);
      if (d.getUTCDay() === 0 || d.getUTCDay() === 6) continue;
      const n = navHistory.length;
      nav *= 1 + 0.0012 + (n % 5) * 0.0004;
      price *= 1 + 0.0007 + (n % 7) * 0.0003;
      const date = d.toISOString().slice(0, 10);
      navHistory.push({ date, nav });
      benchmarkHistory.push({ date, price });
    }
    const kpis = computeLivePerformanceKpis({
      positions: [
        {
          ticker: 'EWT',
          weightPct: 40,
          markPrice: 40,
          effectivePrice: 40,
          isLive: false,
          metricsAsOf: navHistory[navHistory.length - 1]!.date,
          livePriceDate: null,
        },
      ],
      navHistory,
      benchmarkHistory,
      benchmarkTicker: 'SPY',
    });
    expect(kpis.excessReturnPct).not.toBeNull();
    expect(kpis.alphaPct).not.toBeNull();
    expect(kpis.informationRatio).not.toBeNull();
    expect(kpis.benchmarkTicker).toBe('SPY');
  });
});
