'use client';

import {
  ContributionReturnChart,
  type ContributionReturnPoint,
} from '@digithings/web';

import { CATEGORICAL_SERIES } from '@/lib/chart-colors';

export function PortfolioContributionChart({ points }: { points: ContributionReturnPoint[] }) {
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
            Portfolio attribution
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 font-mono text-[0.62rem] text-ink-mute" aria-label="Chart series">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0 w-5 border-t-2 border-accent" aria-hidden />
            Portfolio return
          </span>
          {tickers.map((ticker) => (
            <span key={ticker} className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5" style={{ backgroundColor: colors[ticker] }} aria-hidden />
              {ticker}
            </span>
          ))}
        </div>
      </div>
      {points.length < 2 ? (
        <div className="flex h-72 items-center justify-center px-6 text-sm text-ink-mute">
          A second NAV and position snapshot is needed to draw contribution history.
        </div>
      ) : (
        <ContributionReturnChart points={points} colors={colors} height={340} />
      )}
    </section>
  );
}