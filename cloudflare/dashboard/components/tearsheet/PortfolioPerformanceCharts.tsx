'use client';

import {
  ContributionReturnChart,
  type ContributionReturnPoint,
} from '@digithings/web';
import type { BenchmarkComparison, PerformanceContributionSource } from './types';

import { CATEGORICAL_SERIES } from '@/lib/chart-colors';

/** Degraded-source chrome — only shown when the bars are not the full realized series. */
const CONTRIBUTION_SOURCE_NOTES: Partial<Record<PerformanceContributionSource, string>> = {
  marks_degraded: 'Finalized attribution unavailable — bars fall back to position marks.',
  realized_truncated:
    'Finalized attribution truncated at the read cap — bars may omit older days.',
};

export function PortfolioContributionChart({
  points,
  benchmark,
  source,
  startsOn,
}: {
  points: ContributionReturnPoint[];
  benchmark: BenchmarkComparison | null;
  source?: PerformanceContributionSource;
  /** First date with finalized attribution (#4102); null when not the realized series. */
  startsOn?: string | null;
}) {
  const tickers = [...new Set(points.flatMap((point) => Object.keys(point.contributions)))];
  const colors = Object.fromEntries(
    tickers.map((ticker, index) => [ticker, CATEGORICAL_SERIES[index % CATEGORICAL_SERIES.length]])
  );
  const sourceNote = source ? (CONTRIBUTION_SOURCE_NOTES[source] ?? null) : null;
  // The realized series is final-only, so the bars genuinely begin mid-history
  // (#4102). Say when — but only once there is a chart to annotate; the empty
  // state below already explains why nothing is drawn yet.
  const startNote =
    startsOn && points.length >= 2 && startsOn > points[0].t
      ? `Finalized per-position attribution starts ${startsOn} — earlier days carry no realized attribution.`
      : null;

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
        {sourceNote ? (
          <p
            className="mt-1 font-mono text-[0.62rem] text-warn"
            data-testid="contribution-source-note"
            role="status"
          >
            {sourceNote}
          </p>
        ) : null}
        {startNote ? (
          <p
            className="mt-1 font-mono text-[0.62rem] text-ink-mute"
            data-testid="contribution-start-note"
            role="status"
          >
            {startNote}
          </p>
        ) : null}
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
          A second performance and position snapshot is needed to draw contribution history.
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
