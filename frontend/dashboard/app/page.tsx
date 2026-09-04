'use client';

import { useEffect, useMemo, useState } from 'react';
import { useDashboard } from '@/lib/dashboard-context';
import { useLiveBriefKpis } from '@/lib/hooks/use-live-brief-kpis';
import type { ResearchRunDiagnostics, BenchmarkHistoryMap, NavChartPoint } from '@/lib/types';
import {
  DEFAULT_BRIEF_BENCHMARK_TICKER,
  pickBriefBenchmarkTicker,
} from '@/lib/benchmark-tickers';
import { fetchResearchRunDiagnostics } from '@/lib/observability-queries';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { EmptyState } from '@digithings/web';
import PageSkeleton from '@/components/page-skeleton';
import {
  DailyBriefWorkspace,
  type BriefRunHealth,
} from '@/components/today/daily-brief-workspace';
import { selectBriefLedgerDayEvents } from '@/lib/brief-book-event';
import { buildDisplayRationaleByTicker } from '@/lib/pm-rationale';
import { committedBookDate } from '@/lib/dashboard-ssot';
import {
  buildPerformanceSsotMeta,
  isLiveMarksOverlay,
  persistedHeadlinesFromNav,
} from '@/lib/performance-ssot';
// Performance SSOT (#3580): persisted headlines from the same accounting NAV
// adapter as Tearsheet (`getPerformanceBundle` / public_accounting_nav_history).
// Live marks are a badged overlay only — never a silent second truth.

/**
 * Portfolio vs benchmark over the aligned return window (first portfolio point →
 * last portfolio point, clipped to available benchmark history). `startDate` keeps the label
 * honest ("since {date}", not a dishonest "inception"). Defaults to SPY when present.
 */
function inceptionVsBenchmark(
  snaps: NavChartPoint[],
  benchmarks: BenchmarkHistoryMap
): { ticker: string; portPct: number; benchPct: number; excessPct: number; startDate: string } | null {
  const ticker = pickBriefBenchmarkTicker(benchmarks);
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
  const [runDiagnostics, setRunDiagnostics] = useState<ResearchRunDiagnostics[]>([]);

  useEffect(() => {
    if (!dashboardDate) return;
    let cancelled = false;

    void fetchResearchRunDiagnostics()
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
              className="mt-5 inline-flex items-center border border-hair px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-ink/[0.06]"
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
  const positionDates = (data.position_history ?? []).map((row) => row.date);
  const bookWeightInvestedPct = positions
    .filter((p) => p.ticker.trim().toUpperCase() !== 'CASH')
    .reduce((sum, p) => sum + (p.weight_actual ?? 0), 0);
  const persisted = persistedHeadlinesFromNav(performanceHistoryResolved, {
    bookWeightInvestedPct,
    metricsInvestedPct: data.server_portfolio_metrics?.invested_pct ?? null,
  });
  const performanceSsot = buildPerformanceSsotMeta({
    navRows: performanceHistoryResolved.map((row) => ({
      date: row.date,
      nav: row.nav,
      invested_pct: row.invested_pct ?? null,
      day_return_pct: row.day_return_pct ?? null,
      source: row.source ?? 'legacy_nav_history',
      contract: row.contract ?? 'legacy_estimate',
    })),
    metricsAsOf:
      data.server_portfolio_metrics?.as_of_date ?? data.server_portfolio_metrics?.date ?? null,
    snapshotDate: latestDate,
    positionDates,
    positionMetricsAsOf: positions.map((p) => p.metrics_as_of ?? null),
    bookWeightInvestedPct,
    metricsInvestedPct: data.server_portfolio_metrics?.invested_pct ?? null,
  });
  // Book as-of = committedBookDate — never imply Sep-4 chrome on yesterday's book.
  const bookAsOf =
    committedBookDate(latestDate, positionDates) ??
    performanceSsot.bookAsOf ??
    persisted.navAsOf;
  const liveOverlay = isLiveMarksOverlay(liveKpis?.liveVsMarkPct);
  // Persisted path matches Tearsheet when live overlay is off; live marks are badged.
  const sincePct = liveOverlay
    ? (liveKpis?.sinceInceptionPct ?? persisted.sinceInceptionPct)
    : persisted.sinceInceptionPct;
  const sinceDate = liveKpis?.sinceInceptionStartDate ?? persisted.sinceInceptionStartDate;
  const dailyRet = liveOverlay
    ? (liveKpis?.dayReturnPct ?? persisted.dayReturnPct)
    : persisted.dayReturnPct;
  const priceAsOf = liveOverlay
    ? (liveKpis?.priceAsOfDate ?? bookAsOf)
    : (persisted.navAsOf ?? bookAsOf);
  // Excess / alpha / IR: live overlay when active; else honest endpoint blurb.
  // Alpha/IR stay fail-closed without live overlap — never invent.
  const excessPct = liveOverlay
    ? (liveKpis?.excessReturnPct ?? benchmarkBlurb?.excessPct ?? null)
    : (benchmarkBlurb?.excessPct ?? liveKpis?.excessReturnPct ?? null);
  const benchTicker =
    liveKpis?.benchmarkTicker ??
    benchmarkBlurb?.ticker ??
    (excessPct != null ? DEFAULT_BRIEF_BENCHMARK_TICKER : null);

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
          alphaPct: liveOverlay ? (liveKpis?.alphaPct ?? null) : null,
          informationRatio: liveOverlay ? (liveKpis?.informationRatio ?? null) : null,
        }}
        metrics={{
          maxDrawdown:
            data.server_portfolio_metrics?.max_drawdown ?? data.calculated?.max_drawdown ?? null,
          volatility:
            data.server_portfolio_metrics?.volatility ?? data.calculated?.volatility ?? null,
        }}
        investedPct={persisted.investedPct}
        performanceSsot={performanceSsot}
        liveMarks={liveOverlay}
        positions={positions}
        actionables={strategy.actionableItems ?? []}
        risks={strategy.riskItems ?? []}
        theses={strategy.theses ?? []}
        contextBullets={data.snapshot_context_bullets ?? []}
        // Brief/session date = digest as-of, not lagged book NAV. Using bookAsOf
        // here previously surfaced Aug 25 VGK next to an Aug 27 digest decision.
        ledgerDayEvents={selectBriefLedgerDayEvents(data.position_events, latestDate)}
        runHealth={latestDate ? runHealth : null}
        runDiagnostics={runDiagnostics}
        positionDates={positionDates}
      />
    </div>
  );
}
