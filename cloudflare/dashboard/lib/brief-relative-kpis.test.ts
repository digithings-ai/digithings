import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  computeLivePerformanceKpis,
  MIN_OVERLAP_DAYS,
} from '@digithings/web';
import {
  DEFAULT_BRIEF_BENCHMARK_TICKER,
  pickBriefBenchmarkTicker,
} from '@/lib/benchmark-tickers';
import type { BenchmarkHistoryMap } from '@/lib/types';

const here = dirname(fileURLToPath(import.meta.url));

/** Varying daily moves so OLS β / IR have non-zero sample variance. */
function tradingDays(count: number, startIso = '2026-06-01'): Array<{ date: string; nav: number; price: number }> {
  const out: Array<{ date: string; nav: number; price: number }> = [];
  let nav = 100;
  let price = 500;
  const start = Date.parse(`${startIso}T00:00:00Z`);
  for (let i = 0; out.length < count; i++) {
    const d = new Date(start + i * 86_400_000);
    if (d.getUTCDay() === 0 || d.getUTCDay() === 6) continue;
    nav *= 1 + 0.001 + (out.length % 5) * 0.0003;
    price *= 1 + 0.0005 + (out.length % 7) * 0.0002;
    out.push({ date: d.toISOString().slice(0, 10), nav, price });
  }
  return out;
}

describe('Brief relative KPIs (excess / alpha / SPY SSOT)', () => {
  it('defaults the brief benchmark ticker to SPY when history exists', () => {
    expect(DEFAULT_BRIEF_BENCHMARK_TICKER).toBe('SPY');
    const benchmarks: BenchmarkHistoryMap = {
      QQQ: { current: 400, history: [{ date: '2026-06-23', price: 400 }] },
      SPY: { current: 500, history: [{ date: '2026-06-23', price: 500 }] },
    };
    expect(pickBriefBenchmarkTicker(benchmarks)).toBe('SPY');
  });

  it('falls back to another dashboard ticker only when SPY history is absent', () => {
    const benchmarks: BenchmarkHistoryMap = {
      QQQ: { current: 400, history: [{ date: '2026-06-23', price: 400 }] },
    };
    expect(pickBriefBenchmarkTicker(benchmarks)).toBe('QQQ');
  });

  it('computes non-null excess and alpha when NAV + SPY series exist with enough overlap', () => {
    const series = tradingDays(MIN_OVERLAP_DAYS + 5);
    const kpis = computeLivePerformanceKpis({
      positions: [
        {
          ticker: 'EWT',
          weightPct: 50,
          markPrice: 50,
          effectivePrice: 50,
          isLive: false,
          metricsAsOf: series[series.length - 1]!.date,
          livePriceDate: null,
        },
      ],
      navHistory: series.map((p) => ({ date: p.date, nav: p.nav })),
      benchmarkHistory: series.map((p) => ({ date: p.date, price: p.price })),
      benchmarkTicker: DEFAULT_BRIEF_BENCHMARK_TICKER,
    });
    expect(kpis.benchmarkTicker).toBe('SPY');
    expect(kpis.excessReturnPct).not.toBeNull();
    expect(kpis.alphaPct).not.toBeNull();
    expect(kpis.informationRatio).not.toBeNull();
  });

  it('dashboard Brief benches use NAV-aligned paginated fetchComparablePriceHistory', () => {
    const src = readFileSync(join(here, 'queries.ts'), 'utf8');
    expect(src).toContain('fetchComparablePriceHistory');
    expect(src).toMatch(/await fetchComparablePriceHistory\(\s*\[\.\.\.DASHBOARD_BENCHMARK_TICKERS\]/);
    // Guard the prior truncation path: multi-ticker select without pagination.
    expect(src).not.toContain(".in('ticker', [...DASHBOARD_BENCHMARK_TICKERS])\n      .gte('date', benchCutoff)");
  });
});
