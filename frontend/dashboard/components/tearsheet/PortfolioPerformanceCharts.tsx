'use client';

import {
  ContributionReturnChart,
  type ContributionReturnPoint,
} from '@digithings/web';
import type { BenchmarkComparison } from './types';

import { CATEGORICAL_SERIES } from '@/lib/chart-colors';

export function PortfolioContributionChart({
  points,
  benchmark,
}: {
  points: ContributionReturnPoint[];
  benchmark: BenchmarkComparison | null;
}) {
  const tickers = [...new Set(points.flatMap((point) => Object.keys(point.contributions)))];
  const colors = Object.fromEntries(
    tickers.map((ticker, index) => [ticker, CATEGORICAL_SERIES[index % CATEGORICAL_SERIES.length]])
  );

  return (
    <section
      data-testid="portfolio-contribution-chart"
      className="border-x border-b border-hair bg-surface"
      aria-labelledby="portfolio-contribution-title"
    >
      <div className="flex flex-col gap-3 border-b border-hair px-5 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
            cumulative contribution · percentage points
          </p>
          <h2 id="portfolio-contribution-title" className="font-display text-xl text-ink">
            Return contribution
          </h2>
        </div>
        {/* No per-asset legend — it cannot scale with a long history. Per-asset
            identification lives in the hover popup, color-coded per series.
            Benchmark selection lives in the page-global control above the
            scoreboard — not inside this chart chrome. */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 font-mono text-[0.62rem] text-ink-mute" aria-label="Chart series">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0 w-5 border-t-2 border-accent" aria-hidden />
            Portfolio return
          </span>
          {benchmark ? (
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0 w-5 border-t border-dashed border-ink-soft" aria-hidden />
              {benchmark.ticker}
            </span>
          ) : null}
        </div>
      </div>
      {points.length < 2 ? (
        <div className="flex h-72 items-center justify-center px-6 text-sm text-ink-mute">
          A second NAV and position snapshot is needed to draw contribution history.
        </div>
      ) : (
        <ContributionReturnChart
          points={points}
          colors={colors}
          height={340}
          benchmark={benchmark ? { label: benchmark.ticker, values: benchmark.series.map((point) => point.returnPct) } : undefined}
          ariaLabel="Portfolio return contribution by factor"
        />
      )}
    </section>
  );
}
