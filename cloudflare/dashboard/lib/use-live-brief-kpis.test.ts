import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { computeLivePerformanceKpis, MIN_OVERLAP_DAYS } from '@digithings/web';
import type { BenchmarkHistoryMap, NavChartPoint } from '@/lib/types';

// The live quote lane needs a Supabase client + DOM effects; the seam rebase is
// pure, so stub the lane out and render the hook's initial memo.
vi.mock('@/lib/hooks/use-live-prices', () => ({ useLivePrices: () => ({}) }));

import { useLiveBriefKpis } from './hooks/use-live-brief-kpis';

/** Varying daily moves so OLS β / IR have non-zero sample variance. */
function tradingDays(
  count: number,
  startIso: string,
  navStart: number
): Array<{ date: string; nav: number; price: number }> {
  const out: Array<{ date: string; nav: number; price: number }> = [];
  let nav = navStart;
  let price = 500;
  const start = Date.parse(`${startIso}T00:00:00Z`);
  for (let i = 0; out.length < count; i++) {
    const d = new Date(start + i * 86_400_000);
    if (d.getUTCDay() === 0 || d.getUTCDay() === 6) continue;
    const n = out.length;
    nav *= 1 + 0.0008 + (n % 5) * 0.0003;
    price *= 1 + 0.0005 + (n % 7) * 0.0002;
    out.push({ date: d.toISOString().slice(0, 10), nav, price });
  }
  return out;
}

function Probe({ nav, benchmarks }: { nav: NavChartPoint[]; benchmarks: BenchmarkHistoryMap }) {
  const kpis = useLiveBriefKpis([], nav, benchmarks, 0);
  return createElement('pre', {
    id: 'kpis',
    dangerouslySetInnerHTML: { __html: JSON.stringify(kpis) },
  });
}

function readKpis(html: string): ReturnType<typeof computeLivePerformanceKpis> | null {
  const match = html.match(/<pre id="kpis">([\s\S]*?)<\/pre>/);
  if (!match) throw new Error('live KPI probe did not render');
  return JSON.parse(match[1]);
}

describe('useLiveBriefKpis NAV seam rebase (#3935)', () => {
  it('rebases the live-overlay window on the current source run', () => {
    const legacy = tradingDays(5, '2026-09-01', 90).map((p) => ({
      ...p,
      source: 'legacy_nav_history',
      series_seam: false,
    }));
    const finalized = tradingDays(MIN_OVERLAP_DAYS + 6, '2026-09-08', 100).map((p, i) => ({
      ...p,
      source: 'finalized_accounting',
      series_seam: i === 0,
    }));
    const nav = [...legacy, ...finalized];
    const benchmarks: BenchmarkHistoryMap = {
      SPY: {
        current: nav.at(-1)?.price ?? 500,
        history: nav.map((p) => ({ date: p.date, price: p.price })),
      },
    };

    const kpis = readKpis(renderToStaticMarkup(createElement(Probe, { nav, benchmarks })));
    const expected = computeLivePerformanceKpis({
      positions: [],
      navHistory: finalized.map((p) => ({ date: p.date, nav: p.nav })),
      benchmarkHistory: nav.map((p) => ({ date: p.date, price: p.price })),
      benchmarkTicker: 'SPY',
    });

    expect(kpis).not.toBeNull();
    expect(kpis!.sinceInceptionStartDate).toBe(finalized[0]!.date);
    expect(expected.alphaPct).not.toBeNull();
    // Identical to the post-seam run alone — the seam day never enters β/IR.
    expect(kpis!.sinceInceptionPct).toBeCloseTo(expected.sinceInceptionPct!, 6);
    expect(kpis!.excessReturnPct).toBeCloseTo(expected.excessReturnPct!, 6);
    expect(kpis!.alphaPct).toBeCloseTo(expected.alphaPct!, 6);
    expect(kpis!.informationRatio).toBeCloseTo(expected.informationRatio!, 6);
  });
});
