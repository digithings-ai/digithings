'use client';

import { useMemo } from 'react';
import { useDashboard } from '@/lib/dashboard-context';
import type { BenchmarkHistoryMap, NavChartPoint } from '@/lib/types';
import { DASHBOARD_BENCHMARK_TICKERS } from '@/lib/benchmark-tickers';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import AtlasLoader from '@/components/AtlasLoader';
import { computeEffectivePortfolioRiskMetrics } from '@/lib/portfolio-risk-metrics';
import { MoveHero } from '@/components/today/move-hero';
import { WhyToday } from '@/components/today/why-today';
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

/** Pull a short, human one-liner out of the PM allocation memo (shape-agnostic). */
function summarizeMemo(memo: unknown): string | null {
  const truncate = (s: string, n = 240): string =>
    s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s;
  if (!memo) return null;
  if (typeof memo === 'string') return memo.trim() ? truncate(memo.trim()) : null;
  if (typeof memo === 'object') {
    const m = memo as Record<string, unknown>;
    for (const k of ['summary', 'rationale', 'memo', 'thesis', 'headline', 'text']) {
      const v = m[k];
      if (typeof v === 'string' && v.trim()) return truncate(v.trim());
    }
  }
  return null;
}

// ─── Today ──────────────────────────────────────────────────────────────────────

export default function OverviewPage() {
  const { data, loading, error } = useDashboard();

  const benchmarkBlurb = useMemo(() => {
    if (!data?.portfolio?.snapshots?.length || !data.benchmarks) return null;
    return inceptionVsBenchmark(data.portfolio.snapshots, data.benchmarks);
  }, [data]);

  const riskMetrics = useMemo(() => {
    const snaps = data?.portfolio?.snapshots;
    if (!snaps?.length) return null;
    return computeEffectivePortfolioRiskMetrics(data?.server_portfolio_metrics, snaps);
  }, [data?.portfolio?.snapshots, data?.server_portfolio_metrics]);

  if (loading) return <AtlasLoader />;
  if (error || !data)
    return (
      <div className="flex items-center justify-center h-screen text-fin-red">
        {error || 'Failed to load'}
      </div>
    );

  const { portfolio, positions } = data;
  const { strategy } = portfolio;
  const regimeLabel = (strategy.regime_label || 'neutral') as string;
  const latestDate = portfolio.meta.last_updated || null;
  const runTypeLabel = portfolio.meta.latest_snapshot_run_type ?? null;

  const pipe = data.pipeline_observability;
  // Only bull/bear debate docs (have net_stance) feed the "why today" roll-up.
  const deliberations = (pipe?.deliberation_transcripts ?? []).filter(
    (d) => d?.payload && typeof d.payload.net_stance === 'string'
  );
  const rebalanceActions = data.portfolio_management?.rebalance_actions ?? [];
  const pmMemoSummary = summarizeMemo(pipe?.pm_allocation_memo);

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
  const navSparkData = navSnaps.slice(-20).map((s) => s.nav);
  const navIndex = navSnaps.length ? navSnaps[navSnaps.length - 1].nav : null;
  const dailyRet =
    navSnaps.length >= 2
      ? ((navSnaps[navSnaps.length - 1].nav - navSnaps[navSnaps.length - 2].nav) /
          navSnaps[navSnaps.length - 2].nav) *
        100
      : null;

  return (
    <div className={`${SUBPAGE_MAX} space-y-5 py-4 md:py-7`}>
      <MoveHero
        regime={strategy.regime}
        regimeLabel={regimeLabel}
        asOf={latestDate}
        runType={runTypeLabel}
        actions={rebalanceActions}
        rationaleByTicker={rationaleByTicker}
        nav={{
          index: navIndex,
          dailyPct: dailyRet,
          benchTicker: benchmarkBlurb?.ticker ?? null,
          excessPct: benchmarkBlurb?.excessPct ?? null,
          sinceDate: benchmarkBlurb?.startDate ?? null,
        }}
      />

      <WhyToday deliberations={deliberations} pmMemoSummary={pmMemoSummary} />

      <TodaySummaries
        navSpark={navSparkData}
        excessPct={benchmarkBlurb?.excessPct ?? null}
        sharpe={riskMetrics?.sharpe ?? null}
        positions={positions}
        theses={strategy.theses ?? []}
        readSummary={strategy.summary ?? null}
      />
    </div>
  );
}
