'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, ArrowUpRight } from 'lucide-react';
import { Button } from '@digithings/web';
import { useDashboard } from '@/lib/dashboard-context';
import { useAsyncData } from '@/lib/hooks/use-async-data';
import { fetchTickerDossier } from '@/lib/queries';
import type { TickerDossier } from '@/lib/types';
import { buildPipelineHref } from '@/lib/pipeline-links';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import PageSkeleton from '@/components/page-skeleton';
import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';
import { formatPct, pnlColor } from '@/components/ui';
import ConvictionHistory from './ConvictionHistory';

const DEFAULT_VISIBLE_ACTIONS = 6;

function emptyDossier(ticker: string): TickerDossier {
  return {
    ticker,
    analyst: null,
    analystDate: null,
    coverage: null,
    decisions: [],
    latestAttribution: null,
  };
}

function isDateStale(date: string | null): boolean {
  if (!date) return false;
  const yesterday = new Date();
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  return date < yesterday.toISOString().slice(0, 10);
}

function latestDate(values: Array<string | null | undefined>): string | null {
  return values.filter((value): value is string => Boolean(value)).sort().at(-1) ?? null;
}

function earliestDate(values: Array<string | null | undefined>): string | null {
  return values.filter((value): value is string => Boolean(value)).sort()[0] ?? null;
}

function formatWeight(value: number | null | undefined, digits = 1): string {
  return value == null ? '—' : `${value.toFixed(digits)}%`;
}

function formatPrice(value: number | null | undefined): string {
  return value == null ? '—' : `$${value.toFixed(2)}`;
}

function formatWeightChange(value: number | null): string {
  if (value == null) return '—';
  const digits = Math.abs(value) < 0.05 ? 2 : 1;
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}pp`;
}

function eventReason(reason: string | null): string {
  if (!reason) return 'No reason recorded.';
  if (reason.startsWith('Derived from positions book')) {
    return 'Observed from the committed position history.';
  }
  return reason;
}

function Metric({
  label,
  value,
  sub,
  tone = 'text-ink',
}: {
  label: string;
  value: string;
  sub?: string | null;
  tone?: string;
}) {
  return (
    <div className="min-w-0 border-b border-r border-hair px-4 py-4">
      <dt className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
        {label}
      </dt>
      <dd className={`mt-2 font-mono text-lg tabular-nums ${tone}`}>{value}</dd>
      {sub ? <p className="mt-1 text-xs text-ink-mute">{sub}</p> : null}
    </div>
  );
}

function SectionHeading({
  eyebrow,
  title,
  meta,
}: {
  eyebrow: string;
  title: string;
  meta?: string | null;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 border-b border-hair px-4 py-4 md:px-5">
      <div className="space-y-1">
        <p className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
          {eyebrow}
        </p>
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
      </div>
      {meta ? <span className="font-mono text-[11px] text-ink-mute">{meta}</span> : null}
    </div>
  );
}

export default function TickerDossierView({ ticker }: { ticker: string }) {
  const [showAllActions, setShowAllActions] = useState(false);
  const { data, loading: dashboardLoading } = useDashboard();
  const positions = useMemo(() => data?.positions ?? [], [data]);
  const position = useMemo(
    () => positions.find((item) => item.ticker.toUpperCase() === ticker) ?? null,
    [positions, ticker]
  );
  const positionHistory = useMemo(
    () =>
      (data?.position_history ?? [])
        .filter((row) => row.ticker.toUpperCase() === ticker)
        .sort((a, b) => a.date.localeCompare(b.date)),
    [data, ticker]
  );
  const positionEvents = useMemo(
    () =>
      (data?.position_events ?? [])
        .filter((row) => row.ticker.toUpperCase() === ticker && row.event !== 'HOLD')
        .sort((a, b) => b.date.localeCompare(a.date)),
    [data, ticker]
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
            <ArrowLeft size={16} aria-hidden /> Back to Portfolio
          </Link>
          <p className="text-ink-mute">
            Pick a ticker from Holdings or search for one with the command palette.
          </p>
        </div>
      </div>
    );
  }

  if (dashboardLoading || dossierLoading) return <PageSkeleton />;

  const decisions = [...dossier.decisions].sort((a, b) =>
    (b.run_date ?? '').localeCompare(a.run_date ?? '')
  );
  const latestDecision = decisions[0] ?? null;
  const latestDecisionDate = latestDecision?.run_date ?? null;
  const lastAnalyzed = latestDate([dossier.analystDate, latestDecisionDate]);
  const stale = isDateStale(lastAnalyzed);
  const held = position != null;
  const wasHeld = positionHistory.some((row) => row.weight_pct > 0) || positionEvents.length > 0;
  const sinceEntry = position?.since_entry_return_pct ?? position?.unrealized_pnl_pct ?? null;
  const companyName = position && position.name !== ticker ? position.name : null;
  const currentStance = latestDecision?.stance || dossier.analyst?.stance || null;
  const currentConviction = latestDecision?.conviction ?? dossier.analyst?.conviction_score ?? null;
  const pipelineHref = buildPipelineHref({
    date: lastAnalyzed,
    stage: lastAnalyzed ? 'selection' : null,
  });
  const firstHeldDate = earliestDate([
    position?.entry_date,
    ...positionHistory.filter((row) => row.weight_pct > 0).map((row) => row.date),
    ...positionEvents.filter((row) => row.event === 'OPEN').map((row) => row.date),
  ]);
  const exitDate = latestDate([
    ...positionEvents.filter((row) => row.event === 'EXIT').map((row) => row.date),
    ...(!held ? positionHistory.map((row) => row.date) : []),
  ]);
  const recordedSpan = firstHeldDate
    ? `${firstHeldDate}–${held ? 'present' : exitDate ?? 'unknown'}`
    : null;
  const currentLegStart = held
    ? latestDate([
        ...positionEvents.filter((row) => row.event === 'OPEN').map((row) => row.date),
        position.entry_date,
        firstHeldDate,
      ])
    : null;
  const stateLabel = held
    ? 'held'
    : wasHeld
      ? 'Previously held'
      : dossier.analyst || decisions.length
        ? 'covered · unheld'
        : 'not held';
  const latestAttribution = dossier.latestAttribution ?? null;
  const hasAnything = Boolean(
    dossier.analyst || decisions.length || held || wasHeld || latestAttribution
  );
  const rationale = position?.rationale || position?.pm_notes || null;
  const visiblePositionEvents = showAllActions
    ? positionEvents
    : positionEvents.slice(0, DEFAULT_VISIBLE_ACTIONS);
  const hiddenActionCount = positionEvents.length - DEFAULT_VISIBLE_ACTIONS;

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="holdings" />
      <main className={`${SUBPAGE_MAX} flex-1 space-y-6 py-5 md:py-6`}>
        <Link
          href="/portfolio"
          className="inline-flex items-center gap-2 text-sm text-accent hover:underline"
        >
          <ArrowLeft size={16} aria-hidden /> Back to Portfolio
        </Link>

        <header
          data-testid="dossier-command-band"
          aria-label="Ticker dossier summary"
          className="dossier-command grid grid-cols-1 border-y border-hair bg-surface/[0.82] lg:grid-cols-[minmax(14rem,1.15fr)_minmax(0,2fr)_auto]"
        >
          <div
            data-region="identity"
            className="flex flex-col justify-center gap-2 border-b border-hair p-5 lg:border-b-0 lg:border-r"
          >
            <div className="flex flex-wrap items-baseline gap-2">
              <h1 className="font-mono text-4xl font-medium leading-none text-ink md:text-5xl">
                {ticker}
              </h1>
              <span className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
                {stateLabel}
              </span>
            </div>
            {companyName ? <p className="text-sm text-ink-soft">{companyName}</p> : null}
            <div className="mt-1 flex items-center gap-2">
              <span className="text-sm font-medium capitalize text-ink">
                {currentStance || 'No current view'}
              </span>
              {currentConviction != null ? (
                <SignedConvictionBadge value={currentConviction} />
              ) : null}
            </div>
          </div>

          <dl data-region="metrics" className="m-0 grid grid-cols-3 border-l border-t border-hair">
            <Metric
              label={held ? 'Current weight' : 'Position'}
              value={held ? formatWeight(position.weight_actual, 2) : wasHeld ? 'Closed' : 'Not held'}
              sub={held && position.weight_target != null
                ? `target ${formatWeight(position.weight_target)}`
                : recordedSpan}
            />
            <Metric
              label="Since entry"
              value={held && sinceEntry != null ? formatPct(sinceEntry) : '—'}
              tone={held && sinceEntry != null ? pnlColor(sinceEntry) : 'text-ink-mute'}
              sub={held ? position.entry_date : wasHeld ? 'No current position' : null}
            />
            <Metric
              label="Entry"
              value={held ? formatPrice(position.entry_price) : firstHeldDate ?? '—'}
              sub={held ? position.entry_date : null}
            />
          </dl>

          <div
            data-region="stamp"
            className="flex min-w-0 flex-col items-start justify-center gap-1 border-t border-hair p-5 font-mono text-[0.65rem] uppercase tracking-wider text-ink-mute lg:min-w-[9rem] lg:items-end lg:border-l lg:border-t-0"
          >
            <span>latest analysis</span>
            <strong className="font-medium text-accent">
              {lastAnalyzed?.toUpperCase() ?? 'UNKNOWN'}
            </strong>
          </div>
        </header>

        {error ? <p className="text-xs text-warn">{error}</p> : null}

        {!hasAnything ? (
          <section className="border-y border-hair px-5 py-8">
            <h2 className="text-sm font-semibold text-ink">No ticker record yet</h2>
            <p className="mt-2 max-w-2xl text-sm text-ink-mute">
              There is no analyst coverage, decision, or portfolio position on record for{' '}
              <span className="font-mono">{ticker}</span>.
            </p>
            <Link
              href="/pipeline"
              className="mt-4 inline-flex items-center gap-1 text-sm text-accent hover:underline"
            >
              Open Pipeline <ArrowUpRight size={14} aria-hidden />
            </Link>
          </section>
        ) : (
          <>
            <section className="border-y border-hair" data-region="current-view">
              <SectionHeading
                eyebrow="Pipeline assessment"
                title="Current view"
                meta={lastAnalyzed ? `analyzed ${lastAnalyzed}` : 'no analysis date'}
              />
              <div className="grid lg:grid-cols-[minmax(0,1.6fr)_minmax(16rem,0.6fr)]">
                <div className="px-4 py-5 md:px-5">
                  <div className="flex flex-wrap items-center gap-3">
                    <strong className="font-display text-2xl capitalize text-ink">
                      {currentStance || 'No current stance'}
                    </strong>
                    {currentConviction != null ? (
                      <SignedConvictionBadge value={currentConviction} />
                    ) : null}
                  </div>
                  <p className="mt-3 max-w-3xl text-sm leading-relaxed text-ink-soft">
                    {dossier.analyst?.thesis.trim()
                      ? dossier.analyst.thesis
                      : 'The latest analyst record does not include a written thesis.'}
                  </p>
                </div>
                <aside className="border-t border-hair px-4 py-5 lg:border-l lg:border-t-0">
                  <dl className="space-y-3 text-xs">
                    <div className="flex justify-between gap-3">
                      <dt className="text-ink-mute">Analyses on record</dt>
                      <dd className="font-mono text-ink">{decisions.length}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-ink-mute">Latest source</dt>
                      <dd className="font-mono text-ink">Pipeline analysis</dd>
                    </div>
                  </dl>
                  {stale ? (
                    <p className="mt-4 text-xs leading-relaxed text-ink-mute">
                      No newer material change has triggered a full re-analysis.
                    </p>
                  ) : null}
                  <Link
                    href={pipelineHref}
                    className="mt-4 inline-flex items-center gap-1 text-sm text-accent hover:underline"
                  >
                    Open latest analysis <ArrowUpRight size={14} aria-hidden />
                  </Link>
                </aside>
              </div>
            </section>

            <section className="border-y border-hair" data-region="portfolio-position">
              <SectionHeading
                eyebrow="Book action"
                title="Portfolio position"
                meta={firstHeldDate ? `first held ${firstHeldDate}` : null}
              />
              <dl className="grid grid-cols-2 border-l border-t border-hair lg:grid-cols-4">
                <Metric
                  label="State"
                  value={held ? 'Held' : 'No current position'}
                  sub={held
                    ? (position.type?.toLowerCase() ?? 'long')
                    : wasHeld
                      ? 'Previously held'
                      : 'Never held'}
                />
                <Metric
                  label="Allocation"
                  value={held ? formatWeight(position.weight_actual, 2) : '0.00%'}
                  sub={held && position.weight_target != null
                    ? `target ${formatWeight(position.weight_target)}`
                    : null}
                />
                <Metric
                  label={held ? 'Entry mark' : 'First held'}
                  value={held ? formatPrice(position.entry_price) : firstHeldDate ?? '—'}
                  sub={held ? position.entry_date : null}
                />
                <Metric
                  label={held ? 'Current leg' : 'Recorded span'}
                  value={held && currentLegStart
                    ? `${currentLegStart}–present`
                    : recordedSpan ?? '—'}
                />
              </dl>
              {rationale ? (
                <div className="border-t border-hair px-4 py-4 md:px-5">
                  <p className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
                    Portfolio rationale
                  </p>
                  <p className="mt-2 max-w-4xl text-sm leading-relaxed text-ink-soft">{rationale}</p>
                </div>
              ) : null}
            </section>

            <section className="border-y border-hair" data-region="position-history">
              <SectionHeading
                eyebrow="Allocation actions"
                title="Position history"
                meta={`${positionEvents.length} material ${positionEvents.length === 1 ? 'action' : 'actions'}`}
              />
              {positionEvents.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px] text-sm tabular-nums">
                    <thead>
                      <tr className="border-b border-hair text-left font-mono text-[11px] uppercase text-ink-mute">
                        <th className="px-4 py-2.5 font-normal md:px-5">Date</th>
                        <th className="py-2.5 pr-4 font-normal">Action</th>
                        <th className="py-2.5 pr-4 text-right font-normal">Allocation</th>
                        <th className="py-2.5 pr-4 text-right font-normal">Change</th>
                        <th className="py-2.5 pr-4 text-right font-normal">Price</th>
                        <th className="py-2.5 pr-4 font-normal">Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visiblePositionEvents.map((event, index) => (
                        <tr key={`${event.date}-${event.event}-${index}`} className="border-b border-hair/50">
                          <td className="px-4 py-3 font-mono text-xs text-ink-mute md:px-5">
                            {event.date}
                          </td>
                          <td className="py-3 pr-4 font-medium text-ink">{event.event}</td>
                          <td className="py-3 pr-4 text-right text-ink-soft">
                            {formatWeight(event.weight_pct)}
                          </td>
                          <td className="py-3 pr-4 text-right text-ink-soft">
                            {formatWeightChange(event.weight_change_pct)}
                          </td>
                          <td className="py-3 pr-4 text-right text-ink-soft">
                            {formatPrice(event.price)}
                          </td>
                          <td className="max-w-xl py-3 pr-4 text-ink-soft">
                            {eventReason(event.reason)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="px-4 py-6 text-sm text-ink-mute md:px-5">
                  {held
                    ? 'No material allocation changes are recorded after entry.'
                    : 'No portfolio actions are recorded for this ticker.'}
                </p>
              )}
              {hiddenActionCount > 0 ? (
                <div className="flex justify-center border-t border-hair px-4 py-3">
                  <Button
                    dress="reference"
                    variant="quiet"
                    onClick={() => setShowAllActions(!showAllActions)}
                    aria-label={showAllActions
                      ? 'Show fewer position actions'
                      : `Show ${hiddenActionCount} older position actions`}
                  >
                    {showAllActions ? 'Show fewer' : `Show ${hiddenActionCount} older actions`}
                  </Button>
                </div>
              ) : null}
            </section>

            <section className="border-y border-hair" data-region="measured-outcome">
              <SectionHeading
                eyebrow="Performance and lookback"
                title="Measured outcome"
                meta={latestAttribution ? `lookback ending ${latestAttribution.date}` : null}
              />
              <div className="border-b border-hair px-4 py-3 md:px-5">
                <p className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
                  Latest current-book lookback (diagnostic)
                </p>
              </div>
              <dl className="grid grid-cols-2 border-l border-t border-hair lg:grid-cols-4">
                <Metric
                  label="Since entry"
                  value={held && sinceEntry != null ? formatPct(sinceEntry) : '—'}
                  tone={held && sinceEntry != null ? pnlColor(sinceEntry) : 'text-ink-mute'}
                  sub={held ? 'current holding' : 'not available for a closed position'}
                />
                <Metric
                  label="Position return"
                  value={formatPct(latestAttribution?.position_return_pct ?? null)}
                  tone={pnlColor(latestAttribution?.position_return_pct ?? null)}
                  sub={latestAttribution ? 'lookback window (not realized day)' : 'no snapshot'}
                />
                <Metric
                  label="Lookback contribution"
                  value={formatPct(latestAttribution?.contribution_pct ?? null)}
                  tone={pnlColor(latestAttribution?.contribution_pct ?? null)}
                  sub="weight × lookback return"
                />
                <Metric
                  label="Lookback active"
                  value={formatPct(latestAttribution?.total_attribution_pct ?? null)}
                  tone={pnlColor(latestAttribution?.total_attribution_pct ?? null)}
                  sub="versus SPY (same window)"
                />
              </dl>
              {!latestAttribution ? (
                <p className="border-t border-hair px-4 py-4 text-xs text-ink-mute md:px-5">
                  No stored current-book lookback snapshot is available for this ticker.
                </p>
              ) : null}
            </section>

            <ConvictionHistory decisions={decisions} />
          </>
        )}
      </main>
    </div>
  );
}
