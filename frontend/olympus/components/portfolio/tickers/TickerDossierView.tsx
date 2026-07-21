'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { useDashboard } from '@/lib/dashboard-context';
import { useAsyncData } from '@/lib/hooks/use-async-data';
import { fetchTickerDossier } from '@/lib/queries';
import type { TickerDossier } from '@/lib/types';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import PageSkeleton from '@/components/page-skeleton';
import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';
import { Badge, formatPct, pnlColor } from '@/components/ui';
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

  const stateLabel = held
    ? 'held'
    : dossier.analyst || dossier.decisions.length > 0
      ? 'covered · unheld'
      : null;
  const coverageLabel = dossier.analyst
    ? 'analyst'
    : dossier.decisions.length > 0
      ? 'decisions'
      : 'none';

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="holdings" />
      <div className={`${SUBPAGE_MAX} flex-1 space-y-8 py-6 md:py-8`}>
        <Link
          href="/portfolio"
          className="inline-flex items-center gap-2 text-sm text-accent hover:underline"
        >
          <ArrowLeft size={16} /> Back to Portfolio
        </Link>

        <div
          data-testid="dossier-command-band"
          aria-label="Ticker dossier summary"
          className="dossier-command grid grid-cols-1 border-y border-hair bg-surface/[0.82] lg:grid-cols-[minmax(14rem,1.25fr)_minmax(0,2fr)_auto]"
        >
            <div
              data-region="identity"
              className="flex flex-col justify-center gap-2 border-b border-hair p-5 lg:border-b-0 lg:border-r lg:p-6"
            >
              <div className="flex flex-wrap items-baseline gap-2">
                <h1 className="font-mono text-4xl font-medium leading-none tracking-normal text-ink md:text-5xl">
                  {ticker}
                </h1>
                {stateLabel && (
                  <span className="font-mono text-xs uppercase tracking-normal text-ink-mute">
                    {stateLabel}
                  </span>
                )}
              </div>
              {companyName && (
                <p className="text-sm leading-tight text-ink-soft">{companyName}</p>
              )}
              <div className="mt-1 flex flex-wrap items-center gap-2">
                {dossier.analyst?.stance && (
                  <Badge variant="default">
                    <span className="capitalize">{dossier.analyst.stance}</span>
                  </Badge>
                )}
                {dossier.analyst?.conviction_score != null && (
                  <SignedConvictionBadge value={dossier.analyst.conviction_score} />
                )}
              </div>
            </div>

            {held && position ? (
              <dl data-region="metrics" className="m-0 grid grid-cols-3 border-b border-hair lg:border-b-0">
                <div className="flex flex-col justify-center gap-2 border-r border-hair p-4">
                  <dt className="font-mono text-xs font-medium uppercase tracking-normal text-ink-mute">
                    weight
                  </dt>
                  <dd className="font-mono text-lg tabular-nums text-ink">
                    {position.weight_actual.toFixed(2)}%
                  </dd>
                  {position.weight_target != null &&
                    Math.abs(position.weight_target - position.weight_actual) >= 0.05 && (
                      <p className="font-mono text-xs text-ink-mute">
                        target {position.weight_target.toFixed(1)}%
                      </p>
                    )}
                </div>

                <div className="flex flex-col justify-center gap-2 border-r border-hair p-4">
                  <dt className="font-mono text-xs font-medium uppercase tracking-normal text-ink-mute">
                    since entry
                  </dt>
                  <dd
                    className={`font-mono text-lg tabular-nums ${pnlColor(sinceEntry)} ${sinceEntry == null ? 'text-ink-mute' : ''}`}
                  >
                    {sinceEntry != null ? formatPct(sinceEntry) : '—'}
                  </dd>
                </div>

                <div className="flex flex-col justify-center gap-2 p-4">
                  <dt className="font-mono text-xs font-medium uppercase tracking-normal text-ink-mute">
                    entry
                  </dt>
                  <dd className="font-mono text-lg tabular-nums text-ink">
                    {position.entry_price != null ? `$${position.entry_price.toFixed(2)}` : '—'}
                  </dd>
                  {position.entry_date && (
                    <p className="font-mono text-xs text-ink-mute">{position.entry_date}</p>
                  )}
                </div>
              </dl>
            ) : (
              <dl data-region="metrics" className="m-0 grid grid-cols-3 border-b border-hair lg:border-b-0">
                <div className="flex min-w-0 flex-col justify-center gap-2 border-r border-hair p-4">
                  <dt className="font-mono text-xs font-medium uppercase leading-tight tracking-normal text-ink-mute">
                    position
                  </dt>
                  <dd className="m-0 font-mono text-sm text-ink">not held</dd>
                </div>
                <div className="flex min-w-0 flex-col justify-center gap-2 border-r border-hair p-4">
                  <dt className="font-mono text-xs font-medium uppercase leading-tight tracking-normal text-ink-mute">
                    coverage
                  </dt>
                  <dd className="m-0 font-mono text-sm text-ink">{coverageLabel}</dd>
                </div>
                <div className="flex min-w-0 flex-col justify-center gap-2 p-4">
                  <dt className="font-mono text-xs font-medium uppercase leading-tight tracking-normal text-ink-mute">
                    decisions
                  </dt>
                  <dd className="m-0 font-mono text-sm tabular-nums text-ink">
                    {dossier.decisions.length}
                  </dd>
                </div>
              </dl>
            )}

            <div
              data-region="stamp"
              className="flex min-w-0 flex-col items-start justify-center gap-1 border-t border-hair p-5 font-mono text-xs uppercase tracking-normal text-ink-mute lg:min-w-[9rem] lg:items-end lg:border-l lg:border-t-0 lg:p-6"
            >
              <span>as of</span>
              <strong className="font-medium text-accent">
                {lastAnalyzed?.toUpperCase() ?? 'UNKNOWN'}
              </strong>
            </div>
        </div>

        {error ? (
          <p className="text-xs text-warn">{error}</p>
        ) : null}

        {!hasAnything ? (
          <p className="border-y border-hair px-5 py-6 text-ink-mute">
            We don&apos;t have analyst coverage, decisions, or a position on record for{' '}
            <span className="font-mono">{ticker}</span>.
          </p>
        ) : (
          <>
            <div
              data-region="analyst-workspace"
              className="grid grid-cols-1 border-y border-hair lg:grid-cols-[minmax(0,1fr)_280px]"
            >
              <main className="min-w-0">
                {dossier.analyst ? (
                  <AnalystDossierCard payload={dossier.analyst} asOf={analystDate} />
                ) : (
                  <div className="px-5 py-6 text-sm text-ink-mute md:px-6">
                    No analyst document on record for this ticker yet.
                  </div>
                )}
              </main>

              <aside
                data-region="dossier-context"
                className="border-t border-hair lg:border-l lg:border-t-0"
              >
                <section className="px-5 py-5">
                  <h2 className="font-mono text-xs font-medium uppercase tracking-normal text-ink-mute">
                    Dossier state
                  </h2>
                  <dl className="mt-4 space-y-3 text-xs">
                    <div className="flex items-center justify-between gap-3">
                      <dt className="text-ink-mute">book state</dt>
                      <dd className="m-0 font-mono text-ink">{stateLabel ?? 'uncovered'}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt className="text-ink-mute">coverage</dt>
                      <dd className="m-0 font-mono text-ink">{coverageLabel}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt className="text-ink-mute">decision records</dt>
                      <dd className="m-0 font-mono tabular-nums text-ink">
                        {dossier.decisions.length}
                      </dd>
                    </div>
                  </dl>
                </section>

                {dossier.analyst && stale ? (
                  <section className="border-t border-hair px-5 py-5">
                    <h2 className="font-mono text-xs font-medium uppercase tracking-normal text-ink-mute">
                      Staleness
                    </h2>
                    <p className="mt-3 text-xs leading-relaxed text-ink-soft">
                      Not re-analyzed since {lastAnalyzed}. Delta runs only re-dispatch names
                      whose context changed materially; this is the last full analysis.
                    </p>
                  </section>
                ) : null}

                <div className="border-t border-hair px-5 py-5">
                  <ThesisProvenanceStrip date={lastAnalyzed} documentKey={provenanceKey} />
                </div>
              </aside>
            </div>

            <ConvictionHistory decisions={dossier.decisions} />
          </>
        )}
      </div>
    </div>
  );
}
