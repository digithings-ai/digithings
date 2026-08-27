'use client';

import { useEffect, useMemo, useState } from 'react';
import { useDashboard } from '@/lib/dashboard-context';
import { useLiveBriefKpis } from '@/lib/hooks/use-live-brief-kpis';
import type { AtlasRunDiagnostics, BenchmarkHistoryMap, NavChartPoint } from '@/lib/types';
import { DASHBOARD_BENCHMARK_TICKERS } from '@/lib/benchmark-tickers';
import { fetchAtlasRunDiagnostics } from '@/lib/observability-queries';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { EmptyState } from '@digithings/web';
import PageSkeleton from '@/components/page-skeleton';
import {
  DailyBriefWorkspace,
  type BriefRunHealth,
} from '@/components/today/daily-brief-workspace';
import { buildDisplayRationaleByTicker } from '@/lib/pm-rationale';
// ─── Benchmark blurb (kept from the prior overview; pure, honest window) ────────

function pickBenchmarkTicker(benchmarks: BenchmarkHistoryMap): string | null {
  for (const t of DASHBOARD_BENCHMARK_TICKERS) {
    if (benchmarks[t]?.history?.length) return t;
  }
  return null;
}

/**
 * Portfolio vs benchmark over the aligned return window (first portfolio point →
 * last portfolio point, clipped to available benchmark history). `startDate` keeps the label
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
  const dashboardDate = data?.portfolio?.meta.last_updated ?? null;
  const [runHealth, setRunHealth] = useState<BriefRunHealth | null>();
  const [runDiagnostics, setRunDiagnostics] = useState<AtlasRunDiagnostics[]>([]);

  useEffect(() => {
    if (!dashboardDate) return;
    let cancelled = false;

    void fetchAtlasRunDiagnostics()
      .then((runs) => {
        if (cancelled) return;
        setRunDiagnostics(runs);
        const latestForDate = runs.find((run) => run.run_date === dashboardDate) ?? null;
        setRunHealth(
          latestForDate
            ? {
                status: latestForDate.status,
                runDate: latestForDate.run_date,
                finishedAt: latestForDate.finished_at,
                segmentsOk: latestForDate.segments_ok,
                segmentsTotal: latestForDate.segments_total,
                segmentsCarried: latestForDate.segments_carried,
                segmentsFailed: latestForDate.segments_failed,
                durationS: latestForDate.duration_s,
              }
            : null
        );
      })
      .catch(() => {
        if (!cancelled) {
          setRunHealth(null);
          setRunDiagnostics([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [dashboardDate]);

  const benchmarkBlurb = useMemo(() => {
    if (!data?.portfolio?.snapshots?.length || !data.benchmarks) return null;
    return inceptionVsBenchmark(data.portfolio.snapshots, data.benchmarks);
  }, [data]);

  const performanceHistory = data?.portfolio?.snapshots ?? [];
  const liveKpis = useLiveBriefKpis(
    data?.positions ?? [],
    performanceHistory,
    data?.benchmarks
  );

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

  // Per-ticker PM thesis for Brief / actions (#704). Prefer real H7/H8 narrative;
  // never pass through H8's mechanical sizing fallback (historical docs still
  // carry it until the next pipeline run after #3043).
  const pmActions = (pipe?.pm_rebalance as { actions?: unknown } | null)?.actions;
  const extrasByTicker: Record<string, string> = {};
  for (const pos of positions) {
    const key = pos.ticker.trim().toUpperCase();
    if (!key || key === 'CASH') continue;
    if (typeof pos.rationale === 'string' && pos.rationale.trim()) {
      extrasByTicker[key] = pos.rationale.trim();
    }
  }
  for (const doc of pipe?.deliberation_transcripts ?? []) {
    const key = doc.ticker.trim().toUpperCase();
    if (!key) continue;
    const conclusion =
      typeof doc.payload.conclusion === 'string'
        ? doc.payload.conclusion
        : typeof doc.payload.net_stance_reason === 'string'
          ? doc.payload.net_stance_reason
          : null;
    if (conclusion?.trim() && !extrasByTicker[key]) {
      extrasByTicker[key] = conclusion.trim();
    }
  }
  const rationaleByTicker = buildDisplayRationaleByTicker({
    pmRebalanceActions: pmActions,
    pmDirectionMemo: pipe?.pm_direction_memo ?? null,
    extrasByTicker,
  });

  const performanceHistoryResolved = portfolio.snapshots ?? [];
  // The book's own as-of (latest performance-history point) — deliberately NOT
  // latestDate (the digest date): research publishes daily even when the
  // book-persistence half is frozen (#1555), and book surfaces must carry
  // their own date rather than borrow the digest's freshness.
  const bookAsOf = liveKpis?.bookNavDate ?? (performanceHistoryResolved.length
    ? performanceHistoryResolved[performanceHistoryResolved.length - 1].date
    : null);
  const priceAsOf = liveKpis?.priceAsOfDate ?? bookAsOf;
  // Percentage returns only — never lead with the base-100 NAV index.
  // Prefer the shared live KPI path; fall back to snapshot ratio (same formula).
  const initialPortfolioValue = performanceHistoryResolved.length
    ? performanceHistoryResolved[0].nav
    : null;
  const latestPortfolioValue = liveKpis?.liveNav ?? (performanceHistoryResolved.length
    ? performanceHistoryResolved[performanceHistoryResolved.length - 1].nav
    : null);
  const sincePct =
    liveKpis?.sinceInceptionPct ??
    (latestPortfolioValue != null && initialPortfolioValue != null && initialPortfolioValue > 0
      ? (latestPortfolioValue / initialPortfolioValue - 1) * 100
      : null);
  const sinceDate = liveKpis?.sinceInceptionStartDate ?? (performanceHistoryResolved.length
    ? performanceHistoryResolved[0].date
    : null);
  const dailyRet = liveKpis?.dayReturnPct ?? null;
  const excessPct = liveKpis?.excessReturnPct ?? benchmarkBlurb?.excessPct ?? null;
  const benchTicker = liveKpis?.benchmarkTicker ?? benchmarkBlurb?.ticker ?? null;

  return (
    <div className={`${SUBPAGE_MAX} py-4 md:py-7`}>
      <DailyBriefWorkspace
        regime={strategy.regime}
        regimeLabel={regimeLabel}
        headline={strategy.summary || null}
        confidence={strategy.theses?.[0]?.confidence ?? null}
        digestDate={latestDate}
        bookDate={bookAsOf}
        runType={runTypeLabel}
        actions={rebalanceActions}
        rationaleByTicker={rationaleByTicker}
        returns={{
          sincePct,
          sinceDate,
          dailyPct: dailyRet,
          dailyAsOf: priceAsOf,
          sinceAsOf: priceAsOf,
          benchTicker,
          excessPct,
          excessAsOf: priceAsOf,
          alphaPct: liveKpis?.alphaPct ?? null,
          informationRatio: liveKpis?.informationRatio ?? null,
        }}
        metrics={{
          maxDrawdown:
            data.server_portfolio_metrics?.max_drawdown ?? data.calculated?.max_drawdown ?? null,
          volatility:
            data.server_portfolio_metrics?.volatility ?? data.calculated?.volatility ?? null,
        }}
        investedPct={
          data.server_portfolio_metrics?.invested_pct ?? data.calculated?.total_invested ?? null
        }
        positions={positions}
        actionables={strategy.actionableItems ?? []}
        risks={strategy.riskItems ?? []}
        theses={strategy.theses ?? []}
        contextBullets={data.snapshot_context_bullets ?? []}
        latestEvent={data.position_events?.[0] ?? null}
        runHealth={latestDate ? runHealth : null}
        runDiagnostics={runDiagnostics}
      />
    </div>
  );
}
