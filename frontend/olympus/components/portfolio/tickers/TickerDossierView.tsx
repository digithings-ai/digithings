'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { useDashboard } from '@/lib/dashboard-context';
import { useAsyncData } from '@/lib/hooks/use-async-data';
import { fetchTickerDossier } from '@/lib/queries';
import type { TickerDossier } from '@/lib/types';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import PageSkeleton from '@/components/page-skeleton';
import { AsOfBadge } from '@/components/shared/as-of-badge';
import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';
import { Badge, StatCard, formatPct, pnlColor } from '@/components/ui';
import { ThesisProvenanceStrip } from '@/components/portfolio/theses/ThesisProvenanceStrip';
import { decisionNodeFor } from '@/lib/holdings-decisions';
import AnalystDossierCard from './AnalystDossierCard';
import ConvictionHistory from './ConvictionHistory';

/**
 * Ticker dossier (#1562 PR2) — the searchable per-ticker analysis surface.
 * Reached from the command palette's "Tickers" group, the Holdings drilldown's
 * "View dossier" link, and the thesis story spine's vehicle rows
 * (`/portfolio/tickers?ticker={T}`).
 *
 * Held-position metrics come from the already-loaded dashboard context
 * (`useDashboard()`), NOT a second query — `getFullDashboardData` already owns
 * the weight/PnL computation and there is no value in re-deriving it here.
 * Everything else (analyst payload, coverage pointer, decision history) is a
 * dedicated fetch via `fetchTickerDossier`.
 */

function emptyDossier(ticker: string): TickerDossier {
  return { ticker, analyst: null, analystDate: null, coverage: null, decisions: [] };
}

/** Date-only staleness fallback — mirrors AsOfBadge's own "older than yesterday" rule
 *  so the frozen-coverage notice and the badge agree on what counts as stale. */
function isDateStale(date: string | null): boolean {
  if (!date) return false;
  const yesterday = new Date();
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  return date < yesterday.toISOString().slice(0, 10);
}

export default function TickerDossierView({ ticker }: { ticker: string }) {
  const { data, loading: dashboardLoading } = useDashboard();
  const positions = useMemo(() => data?.positions ?? [], [data]);
  const position = useMemo(
    () => positions.find((p) => p.ticker.toUpperCase() === ticker) ?? null,
    [positions, ticker]
  );

  const {
    data: dossier,
    loading: dossierLoading,
    error,
  } = useAsyncData<TickerDossier>(
    emptyDossier(ticker),
    () => fetchTickerDossier(ticker),
    [ticker]
  );

  if (!ticker) {
    return (
      <div className="flex min-h-full flex-col">
        <PortfolioSectionNav active="holdings" />
        <div className={`${SUBPAGE_MAX} space-y-4 py-8`}>
          <Link
            href="/portfolio"
            className="inline-flex items-center gap-2 text-sm text-accent hover:underline"
          >
            <ArrowLeft size={16} /> Back to Portfolio
          </Link>
          <p className="text-ink-mute">
            Pick a ticker to open its dossier — try the command palette (⌘K) or a Holdings row.
          </p>
        </div>
      </div>
    );
  }

  if (dashboardLoading || dossierLoading) return <PageSkeleton />;

  const analystDate = dossier.analystDate;
  const latestDecisionDate = dossier.decisions.reduce<string | null>(
    (m, d) => (d.run_date && (!m || d.run_date > m) ? d.run_date : m),
    null
  );
  // Staleness must come from the doc/decision row date, never `coverage.last_updated`
  // (the pointer refreshes daily even while the underlying doc stays frozen — #1562 §0).
  const lastAnalyzed = analystDate ?? latestDecisionDate;
  const stale = isDateStale(lastAnalyzed);
  const held = position != null;
  const sinceEntry = position?.since_entry_return_pct ?? position?.unrealized_pnl_pct ?? null;
  const companyName = position && position.name !== ticker ? position.name : null;
  const provenanceKey = dossier.coverage?.current_recommendation_key ?? decisionNodeFor(ticker);
  const hasAnything = dossier.analyst != null || dossier.decisions.length > 0 || held;

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="holdings" />
      <div className={`${SUBPAGE_MAX} flex-1 space-y-8 py-6 md:py-8`}>
        <div className="space-y-4">
          <Link
            href="/portfolio"
            className="inline-flex items-center gap-2 text-sm text-accent hover:underline"
          >
            <ArrowLeft size={16} /> Back to Portfolio
          </Link>

          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="font-mono text-3xl font-semibold leading-tight text-ink">{ticker}</h1>
              {companyName ? <p className="text-sm text-ink-soft">{companyName}</p> : null}
            </div>
            <AsOfBadge date={lastAnalyzed} />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {dossier.analyst?.stance ? (
              <Badge variant="default">
                <span className="capitalize">{dossier.analyst.stance}</span>
              </Badge>
            ) : null}
            {dossier.analyst?.conviction_score != null ? (
              <SignedConvictionBadge value={dossier.analyst.conviction_score} />
            ) : null}
          </div>

          {error ? <p className="text-xs text-warn">{error}</p> : null}

          {dossier.analyst && stale ? (
            <p className="max-w-2xl text-xs leading-relaxed text-ink-mute">
              Not re-analyzed since {lastAnalyzed} — delta runs only re-dispatch names whose
              context changed materially; a held name is otherwise carried at its drifted
              weight. This is the last full analysis.
            </p>
          ) : null}
        </div>

        {held ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {/* Booked weight is a share, not a signed P&L read — no '+' prefix.
                The PM's target (when it differs post-turnover) reads as context. */}
            <StatCard
              label="Weight"
              value={`${position!.weight_actual.toFixed(2)}%`}
              subtitle={
                position!.weight_target != null &&
                Math.abs(position!.weight_target - position!.weight_actual) >= 0.05
                  ? `target ${position!.weight_target.toFixed(1)}%`
                  : undefined
              }
            />
            <StatCard
              label="Since entry"
              value={sinceEntry != null ? formatPct(sinceEntry) : '—'}
              valueClass={pnlColor(sinceEntry)}
            />
            <StatCard
              label="Entry"
              value={position!.entry_price != null ? `$${position!.entry_price.toFixed(2)}` : '—'}
              subtitle={position!.entry_date ?? undefined}
            />
          </div>
        ) : null}

        {!hasAnything ? (
          <p className="text-ink-mute">
            We don&apos;t have analyst coverage, decisions, or a position on record for{' '}
            <span className="font-mono">{ticker}</span>.
          </p>
        ) : (
          <>
            {dossier.analyst ? (
              <AnalystDossierCard payload={dossier.analyst} asOf={analystDate} />
            ) : (
              <div className="glass-card p-5 text-sm text-ink-mute md:p-6">
                No analyst document on record for this ticker yet.
              </div>
            )}

            <ConvictionHistory decisions={dossier.decisions} />

            <ThesisProvenanceStrip date={lastAnalyzed} documentKey={provenanceKey} />
          </>
        )}
      </div>
    </div>
  );
}
