'use client';

import { useMemo } from 'react';
import { useDashboard } from '@/lib/dashboard-context';
import type { BenchmarkHistoryMap, NavChartPoint } from '@/lib/types';
import { DASHBOARD_BENCHMARK_TICKERS } from '@/lib/benchmark-tickers';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { EmptyState } from '@digithings/web';
import PageSkeleton from '@/components/page-skeleton';
import { MoveHero } from '@/components/today/move-hero';
import { WhatToWatch } from '@/components/today/what-to-watch';
import { BookStrip } from '@/components/today/book-strip';
import { TodaySummaries } from '@/components/today/today-summaries';

// ─── Benchmark blurb (kept from the prior overview; pure, honest window) ────────

function pickBenchmarkTicker(benchmarks: BenchmarkHistoryMap): string | null {
  for (const t of DASHBOARD_BENCHMARK_TICKERS) {
    if (benchmarks[t]?.history?.length) return t;
  }
  return null;
}

/**
 * Portfolio vs benchmark over the aligned window (first NAV snap date → last NAV
 * snap date, clipped to available benchmark history). `startDate` keeps the label
 * honest ("since {date}", not a dishonest "inception").
 */
function inceptionVsBenchmark(
  snaps: NavChartPoint[],
  benchmarks: BenchmarkHistoryMap
): { ticker: string; portPct: number; benchPct: number; excessPct: number; startDate: string } | null {
  const ticker = pickBenchmarkTicker(benchmarks);
  if (!ticker || snaps.length < 2) return null;
  const hist = benchmarks[ticker]?.history;
  if (!hist?.length) return null;
  const sortedBench = [...hist].sort((a, b) => a.date.localeCompare(b.date));
  const first = snaps[0];
  const last = snaps[snaps.length - 1];
  const startBench = sortedBench.find((p) => p.date >= first.date);
  const endBench = [...sortedBench].reverse().find((p) => p.date <= last.date);
  if (!startBench || !endBench || startBench.date > endBench.date) return null;
  if (last.nav <= 0 || first.nav <= 0 || startBench.price <= 0 || endBench.price <= 0) return null;
  const portPct = (last.nav / first.nav - 1) * 100;
  const benchPct = (endBench.price / startBench.price - 1) * 100;
  const startDate = first.date > startBench.date ? first.date : startBench.date;
  return { ticker, portPct, benchPct, excessPct: portPct - benchPct, startDate };
}

// ─── Today ──────────────────────────────────────────────────────────────────────

export default function OverviewPage() {
  const { data, loading, error } = useDashboard();

  const benchmarkBlurb = useMemo(() => {
    if (!data?.portfolio?.snapshots?.length || !data.benchmarks) return null;
    return inceptionVsBenchmark(data.portfolio.snapshots, data.benchmarks);
  }, [data]);

  if (loading) return <PageSkeleton />;
  if (error || !data)
    return (
      <div className={`${SUBPAGE_MAX} py-12`}>
        <EmptyState
          variant="error"
          className="mx-auto max-w-md"
          title="Couldn’t load your dashboard"
          body={error || 'The latest data did not come through. This is usually temporary.'}
          action={
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-5 inline-flex items-center rounded-lg border border-hair px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-ink/[0.06]"
            >
              Try again
            </button>
          }
        />
      </div>
    );

  const { portfolio, positions } = data;
  const { strategy } = portfolio;
  const regimeLabel = (strategy.regime_label || 'neutral') as string;
  const latestDate = portfolio.meta.last_updated || null;
  const runTypeLabel = portfolio.meta.latest_snapshot_run_type ?? null;

  const pipe = data.pipeline_observability;
  const rebalanceActions = data.portfolio_management?.rebalance_actions ?? [];

  // Per-ticker rationale from the Hermes pm-rebalance decision (#704) — joined onto
  // the move by ticker (normalized trim+UPPER).
  const rationaleByTicker: Record<string, string> = {};
  const pmActions = (pipe?.pm_rebalance as { actions?: unknown } | null)?.actions;
  if (Array.isArray(pmActions)) {
    for (const row of pmActions) {
      if (row && typeof row === 'object') {
        const r = row as { ticker?: unknown; rationale?: unknown };
        if (typeof r.ticker === 'string' && typeof r.rationale === 'string' && r.rationale.trim()) {
          rationaleByTicker[r.ticker.trim().toUpperCase()] = r.rationale.trim();
        }
      }
    }
  }

  const navSnaps = portfolio.snapshots ?? [];
  // The book's own as-of (latest nav_history point) — deliberately NOT
  // latestDate (the digest date): research publishes daily even when the
  // book-persistence half is frozen (#1555), and book surfaces must carry
  // their own date rather than borrow the digest's freshness.
  const bookAsOf = navSnaps.length ? navSnaps[navSnaps.length - 1].date : null;
  const navIndex = navSnaps.length ? navSnaps[navSnaps.length - 1].nav : null;
  const navFirst = navSnaps.length ? navSnaps[0].nav : null;
  const sincePct =
    navIndex != null && navFirst != null && navFirst > 0
      ? (navIndex / navFirst - 1) * 100
      : null;
  const sinceDate = navSnaps.length ? navSnaps[0].date : null;
  // Daily delta + benchmark are gated on ≥2 NAV points (empty-state discipline).
  const dailyRet =
    navSnaps.length >= 2
      ? ((navSnaps[navSnaps.length - 1].nav - navSnaps[navSnaps.length - 2].nav) /
          navSnaps[navSnaps.length - 2].nav) *
        100
      : null;

  return (
    <div className={`${SUBPAGE_MAX} py-4 md:py-6`}>
      <section
        data-testid="brief-workspace"
        aria-label="Daily investment brief"
        className="space-y-4"
      >
        <MoveHero
          regime={strategy.regime}
          regimeLabel={regimeLabel}
          headline={strategy.summary || null}
          confidence={strategy.theses?.[0]?.confidence ?? null}
          asOf={latestDate}
          runType={runTypeLabel}
          actions={rebalanceActions}
          rationaleByTicker={rationaleByTicker}
          nav={{
            index: navIndex,
            sincePct,
            sinceDate,
            dailyPct: dailyRet,
            benchTicker: benchmarkBlurb?.ticker ?? null,
            excessPct: benchmarkBlurb?.excessPct ?? null,
            asOfDate: bookAsOf,
          }}
        />

        <div
          data-region="brief-analysis-grid"
          className="grid items-stretch gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.85fr)]"
        >
          <WhatToWatch
            actionables={strategy.actionableItems ?? []}
            risks={strategy.riskItems ?? []}
            asOfDate={latestDate}
          />

          <BookStrip
            positions={positions}
            investedPct={data.server_portfolio_metrics?.invested_pct ?? null}
            asOfDate={bookAsOf}
          />
        </div>

        <TodaySummaries
          positions={positions}
          investedPct={data.server_portfolio_metrics?.invested_pct ?? null}
          theses={strategy.theses ?? []}
          readSummary={strategy.summary ?? null}
          asOfDate={latestDate}
        />
      </section>
    </div>
  );
}
