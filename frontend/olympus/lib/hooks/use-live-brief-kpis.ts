'use client';

/**
 * Live performance KPIs for the Brief scoreboard — same computation path as
 * digiquant.io landing ({@link computeLivePerformanceKpis} in @digithings/web).
 *
 * Relative metrics (excess / alpha / IR) require a NAV-aligned SPY (default)
 * price series from the dashboard benchmarks map. Fail closed when the series
 * is missing or overlap is shorter than {@link MIN_OVERLAP_DAYS}.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  computeLivePerformanceKpis,
  type LivePerformanceKpis,
} from '@digithings/web';
import { pickBriefBenchmarkTicker } from '@/lib/benchmark-tickers';
import { useLivePrices } from '@/lib/hooks/use-live-prices';
import { isQuoteFresh, quoteAgeMs, type LiveQuoteMap } from '@/lib/live-valuation';
import type { BenchmarkHistoryMap, NavChartPoint, Position } from '@/lib/types';

/** Same cadence as AllocationsPositionsTable — keep freshness labels from freezing mid-session. */
const CLOCK_TICK_MS = 30_000;

/**
 * Reference clock for quote freshness. `Date.now()` must not run in render
 * (`react-hooks/purity`); read it in a lazy useState initializer and interval effect.
 */
function useNowMs(intervalMs = CLOCK_TICK_MS): number {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return nowMs;
}

function positionIsLive(ticker: string, quotes: LiveQuoteMap, nowMs: number): boolean {
  const q = quotes[ticker.trim().toUpperCase()];
  if (!q) return false;
  return isQuoteFresh(quoteAgeMs(q.quotedAt, nowMs));
}

function livePriceDate(ticker: string, quotes: LiveQuoteMap, nowMs: number): string | null {
  const q = quotes[ticker.trim().toUpperCase()];
  if (!q || !positionIsLive(ticker, quotes, nowMs)) return null;
  return q.quotedAt.slice(0, 10);
}

export function useLiveBriefKpis(
  positions: Position[],
  navHistory: NavChartPoint[],
  benchmarks: BenchmarkHistoryMap | undefined,
  nowMs?: number
): LivePerformanceKpis | null {
  const ticking = useNowMs();
  const effectiveNowMs = nowMs ?? ticking;
  const tickers = useMemo(
    () =>
      positions
        .map((p) => p.ticker?.trim().toUpperCase())
        .filter((t) => t && t !== 'CASH'),
    [positions]
  );
  const quotes = useLivePrices(tickers);

  return useMemo(() => {
    if (!navHistory.length || !positions.length) return null;
    const benchTicker = benchmarks ? pickBriefBenchmarkTicker(benchmarks) : null;
    const benchmarkHistory =
      benchTicker && benchmarks?.[benchTicker]?.history
        ? benchmarks[benchTicker].history.map((p) => ({ date: p.date, price: p.price }))
        : undefined;

    const kpiPositions = positions
      .filter((p) => p.ticker?.trim().toUpperCase() !== 'CASH')
      .map((p) => {
        const ticker = p.ticker.trim().toUpperCase();
        const mark = p.current_price ?? null;
        const q = quotes[ticker];
        const live = positionIsLive(ticker, quotes, effectiveNowMs);
        const effective = live && q?.price != null && q.price > 0 ? q.price : mark;
        return {
          ticker,
          weightPct: p.weight_actual ?? 0,
          markPrice: mark,
          effectivePrice: effective,
          isLive: live,
          metricsAsOf: p.metrics_as_of ?? null,
          livePriceDate: livePriceDate(ticker, quotes, effectiveNowMs),
        };
      });

    return computeLivePerformanceKpis({
      positions: kpiPositions,
      navHistory: navHistory.map((p) => ({ date: p.date, nav: p.nav })),
      benchmarkHistory,
      benchmarkTicker: benchTicker,
    });
  }, [positions, navHistory, benchmarks, quotes, effectiveNowMs]);
}
