'use client';

import { useEffect, useState } from 'react';
import { useDashboard } from '@/lib/dashboard-context';
import { useLiveBriefKpis } from '@/lib/hooks/use-live-brief-kpis';
import type { ResearchRunDiagnostics } from '@/lib/types';
import { DEFAULT_BRIEF_BENCHMARK_TICKER } from '@/lib/benchmark-tickers';
import { fetchResearchRunDiagnostics } from '@/lib/observability-queries';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { Button, EmptyState } from '@digithings/ui/ui';
import PageSkeleton from '@/components/page-skeleton';
import {
  DailyBriefWorkspace,
  type BriefRunHealth,
} from '@/components/today/daily-brief-workspace';
import { selectBriefLedgerDayEvents } from '@/lib/brief-book-event';
import { buildDisplayRationaleByTicker } from '@/lib/pm-rationale';
import { isCashTicker } from '@/lib/book-reconciliation';
import { isLiveMarksOverlay } from '@/lib/performance-ssot';
// Performance SSOT (#3580): persisted headlines from the same accounting NAV
// adapter as Tearsheet (`getPerformanceBundle` / public_accounting_nav_history).
// Live marks are a badged overlay only — never a silent second truth.

// ─── Today ──────────────────────────────────────────────────────────────────────

export default function OverviewPage() {
  const { data, api, loading, error } = useDashboard();
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


  const performanceHistory = data?.portfolio?.snapshots ?? [];
  const liveKpis = useLiveBriefKpis(
    data?.positions ?? [],
    performanceHistory,
    data?.benchmarks
  );

  if (loading) return <PageSkeleton />;
  if (error || !data || !api)
    return (
      <div className={`${SUBPAGE_MAX} py-12`}>
        <EmptyState
          variant="error"
          className="mx-auto max-w-md"
          title="Couldn’t load your dashboard"
          body={error || 'The latest data did not come through. This is usually temporary.'}
          action={
            <Button
              type="button"
              variant="outline"
              onClick={() => window.location.reload()}
              className="mt-5"
            >
              Try again
            </Button>
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

  // Per-ticker PM thesis for Brief / actions (#704). Prefer real direction/sizing narrative;
  // never pass through sizing's mechanical fallback (historical docs still
  // carry it until the next pipeline run after #3043).
  const pmActions = (pipe?.pm_rebalance as { actions?: unknown } | null)?.actions;
  const extrasByTicker: Record<string, string> = {};
  for (const pos of positions) {
    const key = pos.ticker.trim().toUpperCase();
    if (!key || isCashTicker(key)) continue;
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

  // Scoreboard numbers come from the Workers API (GET /brief + GET /performance):
  // the persisted-vs-overlay decision is made server-side, never re-derived
  // here. The live overlay (Realtime marks) still engages client-side and is
  // always badged — never a silent second truth.
  const positionDates = (data.position_history ?? []).map((row) => row.date);
  const brief = api.brief;
  const perf = api.performance;
  const performanceSsot = perf.ssot;
  const bookAsOf = brief.book_as_of;
  const liveOverlay = isLiveMarksOverlay(liveKpis?.liveVsMarkPct);
  // Persisted path matches Tearsheet when live overlay is off; live marks are badged.
  const sincePct = liveOverlay
    ? (liveKpis?.sinceInceptionPct ?? brief.since_inception_pct)
    : brief.since_inception_pct;
  const sinceDate = liveOverlay
    ? (liveKpis?.sinceInceptionStartDate ?? brief.since_inception_start_date)
    : brief.since_inception_start_date;
  const dailyRet = liveOverlay
    ? (liveKpis?.dayReturnPct ?? brief.day_return_pct)
    : brief.day_return_pct;
  const priceAsOf = liveOverlay
    ? (liveKpis?.priceAsOfDate ?? brief.nav_tip.date ?? bookAsOf)
    : (brief.nav_tip.date ?? bookAsOf);
  // Excess stays on the persisted aligned window unless live marks are badged.
  // Alpha / IR are series metrics — render whenever overlap exists, overlay or not.
  const excessPct = liveOverlay
    ? (liveKpis?.excessReturnPct ?? perf.metrics.excess_return_pct)
    : perf.metrics.excess_return_pct;
  const benchTicker =
    (liveOverlay ? liveKpis?.benchmarkTicker : null) ??
    perf.benchmark.ticker ??
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
          alphaPct: liveOverlay
            ? (liveKpis?.alphaPct ?? perf.metrics.alpha_pct)
            : perf.metrics.alpha_pct,
          informationRatio: liveOverlay
            ? (liveKpis?.informationRatio ?? perf.metrics.information_ratio)
            : perf.metrics.information_ratio,
        }}
        metrics={{
          maxDrawdown:
            data.server_portfolio_metrics?.max_drawdown ?? data.calculated?.max_drawdown ?? null,
          volatility:
            data.server_portfolio_metrics?.volatility ?? data.calculated?.volatility ?? null,
        }}
        investedPct={brief.invested_pct}
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
