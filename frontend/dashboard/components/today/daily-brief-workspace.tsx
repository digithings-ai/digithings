'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  ChartNoAxesCombined,
  GitBranch,
  ListOrdered,
  Shield,
  Wallet,
} from 'lucide-react';
import type {
  ActionableItem,
  ResearchRunDiagnostics,
  DashboardPositionEvent,
  Position,
  RebalanceAction,
  RiskItem,
} from '@/lib/types';
import type { PlanTier } from '@/lib/entitlements';
import { isCashTicker, reconcileBook } from '@/lib/book-reconciliation';
import { buildPipelineHref } from '@/lib/pipeline-links';
import { AsOfBadge, formatAsOf } from '@/components/shared/as-of-badge';
import { formatBriefWeightChange } from '@/lib/brief-book-event';
import { usablePmRationale } from '@/lib/pm-rationale';
import {
  thesisDetailHref,
  tickerDossierHref,
} from '@/lib/portfolio-url-state';
import { EntitledSurface } from '@/components/entitled-surface';
import { PortfolioTeaserSurface } from '@/components/tier/portfolio-teaser-surface';
import {
  metricsDivergenceBadgeLabel,
  navContractBadgeLabel,
  type PerformanceSsotMeta,
} from '@/lib/performance-ssot';
import {
  BriefPipelineHealth,
  type BriefRunHealth,
} from './brief-pipeline-health';
import { activeRebalanceActions, buildBriefHighlight, portfolioActionChip } from './brief-highlight';
import type { TodayThesis } from './today-summaries';

export type { BriefRunHealth };

/** Whole-card drill-in — hover affordance, one destination, no nested micro-links. */
function BriefCardLink({
  href,
  className,
  children,
  'aria-label': ariaLabel,
  'data-testid': testId,
}: {
  href: string;
  className?: string;
  children: ReactNode;
  'aria-label'?: string;
  'data-testid'?: string;
}) {
  return (
    <Link
      href={href}
      aria-label={ariaLabel}
      data-testid={testId}
      className={`block transition-colors hover:bg-ink/[0.03] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-accent ${className ?? ''}`}
    >
      {children}
    </Link>
  );
}

function ClaimLink({
  href,
  children,
  className,
  testId,
}: {
  href: string | null | undefined;
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  if (!href) {
    return <span className={className} data-testid={testId}>{children}</span>;
  }
  return (
    <Link
      href={href}
      data-testid={testId}
      className={`transition-colors hover:text-accent ${className ?? ''}`}
    >
      {children}
    </Link>
  );
}

export interface DailyBriefWorkspaceProps {
  regime: string;
  regimeLabel: string;
  headline: string | null;
  confidence: number | null;
  digestDate: string | null;
  bookDate: string | null;
  runType: string | null;
  actions: RebalanceAction[];
  rationaleByTicker: Record<string, string>;
  returns: {
    sincePct: number | null;
    sinceDate: string | null;
    dailyPct: number | null;
    dailyAsOf: string | null;
    sinceAsOf: string | null;
    benchTicker: string | null;
    excessPct: number | null;
    excessAsOf: string | null;
    alphaPct: number | null;
    informationRatio: number | null;
  };
  metrics: {
    maxDrawdown: number | null;
    volatility: number | null;
  };
  investedPct: number | null;
  /** Performance SSOT chrome (#3580) — contract + metrics lag + marks stamp. */
  performanceSsot?: PerformanceSsotMeta | null;
  /** True when Brief scoreboard uses live price overlay (must be labeled). */
  liveMarks?: boolean;
  positions: Position[];
  actionables: ActionableItem[];
  risks: RiskItem[];
  theses: TodayThesis[];
  contextBullets: string[];
  /**
   * Material position events for the brief/session date only (Portfolio Ledger
   * day summary). Empty → honest empty copy; never an older session's move.
   */
  ledgerDayEvents: DashboardPositionEvent[];
  /** `undefined` while loading, `null` when the public health view has no row. */
  runHealth: BriefRunHealth | null | undefined;
  /** Recent run diagnostics for the Pipeline Health week bar (optional). */
  runDiagnostics?: ResearchRunDiagnostics[];
  /** All position dates, including unpublished rows newer than the snapshot. */
  positionDates?: string[];
  /** Test override for house book gates; production reads the session. */
  tier?: PlanTier;
}

type Tone = 'neutral' | 'positive' | 'negative' | 'warning';

function signedPct(value: number | null): string {
  if (value == null) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;
}

function metricTone(value: number | null): Tone {
  if (value == null || value === 0) return 'neutral';
  return value > 0 ? 'positive' : 'negative';
}

function toneClass(tone: Tone): string {
  if (tone === 'positive') return 'text-up';
  if (tone === 'negative') return 'text-down';
  if (tone === 'warning') return 'text-warn';
  return 'text-ink';
}

function Metric({ label, value, note, tone = 'neutral' }: {
  label: string;
  value: string;
  note?: string | null;
  tone?: Tone;
}) {
  return (
    <div className="min-w-0 border-r border-hair px-4 py-3 last:border-r-0 sm:px-5">
      <dt className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">{label}</dt>
      <dd className={`mt-1 font-mono text-lg font-semibold tabular-nums ${toneClass(tone)}`}>
        {value}
      </dd>
      {note ? <p className="mt-0.5 truncate text-[10px] text-ink-mute">{note}</p> : null}
    </div>
  );
}

function decisionSummary(actions: RebalanceAction[]): {
  label: string;
  detail: string;
  active: RebalanceAction[];
} {
  const active = activeRebalanceActions(actions);
  if (actions.length === 0) {
    return {
      label: 'No decision published',
      detail: 'Awaiting portfolio recommendation',
      active,
    };
  }
  if (active.length === 0) {
    return {
      label: 'Holding the book',
      detail: 'No allocation change recommended',
      active,
    };
  }
  return {
    label: `${active.length} allocation change${active.length === 1 ? '' : 's'}`,
    // Compact action chips only — thesis prose lives in the hero attention.
    detail: active.map((action) => portfolioActionChip(action)).join(' · '),
    active,
  };
}

function statusDot(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized.includes('confirmed') || normalized.includes('active')) return 'bg-accent';
  if (normalized.includes('monitor') || normalized.includes('watch')) return 'bg-warn';
  if (normalized.includes('invalid') || normalized.includes('broken')) return 'bg-down';
  return 'bg-ink-mute/50';
}

const DESTINATIONS = [
  { label: 'Digest', href: null as string | null, icon: BookOpen },
  { label: 'Pipeline', href: '/pipeline', icon: GitBranch },
  { label: 'Performance', href: '/portfolio/performance', icon: ChartNoAxesCombined },
  { label: 'Holdings', href: '/portfolio', icon: Wallet },
  { label: 'Ledger', href: '/portfolio/ledger', icon: ListOrdered },
  { label: 'Theses', href: '/portfolio?tab=theses', icon: Shield },
] as const;

const LEDGER_DAY_PREVIEW = 4;

export function DailyBriefWorkspace({
  headline,
  digestDate,
  bookDate,
  actions,
  rationaleByTicker,
  returns,
  investedPct,
  performanceSsot = null,
  liveMarks = false,
  positions,
  actionables,
  risks,
  theses,
  contextBullets,
  ledgerDayEvents,
  runHealth,
  runDiagnostics = [],
  positionDates = [],
  tier,
}: DailyBriefWorkspaceProps) {
  // `regime`, `regimeLabel`, `confidence`, and `runType` remain on the props
  // contract for callers; the Brief header keeps only the as-of date — no
  // decorative run-type / tone pills (#3036 follow-up).
  const book = reconcileBook(positions, { investedPct });
  const held = book.rows
    .filter((position) => !isCashTicker(position.ticker))
    .sort((a, b) => Math.abs(b.day_change_pct ?? 0) - Math.abs(a.day_change_pct ?? 0));
  const decision = decisionSummary(actions);
  const ledgerPreview = ledgerDayEvents.slice(0, LEDGER_DAY_PREVIEW);
  const highlightEvent = ledgerDayEvents[0] ?? null;
  const highlight = buildBriefHighlight({
    headline,
    actions,
    rationaleByTicker,
    actionables,
    risks,
    contextBullets,
    latestEvent: highlightEvent,
    digestDate,
  });
  const latestThesis = theses[0] ?? null;
  const latestRisk = risks[0] ?? null;
  const latestContext = contextBullets[0] ?? null;
  const digestHref = buildPipelineHref({ date: digestDate, stage: 'synthesis', node: 'digest' });
  const thesesHref = latestThesis?.id
    ? thesisDetailHref(latestThesis.id)
    : '/portfolio?tab=theses';
  const decisionHref =
    decision.active[0] != null
      ? tickerDossierHref(decision.active[0].ticker)
      : buildPipelineHref({ date: digestDate, stage: 'selection', node: 'pm-rebalance' });
  const cashForNote =
    performanceSsot?.investedDefinition === 'accounting_nav_tip' &&
    performanceSsot.tipCashPct != null
      ? performanceSsot.tipCashPct
      : book.cashPct;
  const investedNote =
    performanceSsot?.investedDefinition === 'accounting_nav_tip'
      ? `${cashForNote.toFixed(0)}% cash · accounting tip`
      : performanceSsot?.investedDefinition === 'book_weights'
        ? `${cashForNote.toFixed(0)}% cash · book weights`
        : performanceSsot?.investedDefinition === 'portfolio_metrics'
          ? `${cashForNote.toFixed(0)}% cash · metrics`
          : `${cashForNote.toFixed(0)}% cash`;
  const showNavContract =
    performanceSsot?.navContract &&
    performanceSsot.navContract !== 'empty' &&
    !(liveMarks && performanceSsot.navContract === 'finalized_accounting');
  const divergenceLabel = performanceSsot
    ? metricsDivergenceBadgeLabel(performanceSsot)
    : null;

  // Book-monitor scroll-edge cue (full-UI-suite critique, P2; refined per
  // CodeRabbit on PR #2287): only shown while the table genuinely overflows
  // its container AND the user has not already scrolled to the end -- a
  // static, always-on cue would keep signaling "more here" even once
  // there is nothing left to reveal. Watches the TABLE's own width (a
  // ResizeObserver on the scroll container alone would miss content
  // getting wider without the container itself resizing).
  const bookScrollRef = useRef<HTMLDivElement>(null);
  const bookTableRef = useRef<HTMLTableElement>(null);
  const [showBookFade, setShowBookFade] = useState(false);

  useEffect(() => {
    const container = bookScrollRef.current;
    const table = bookTableRef.current;
    if (!container || !table) {
      setShowBookFade(false);
      return;
    }

    const EPSILON = 1; // sub-pixel rounding slack
    const update = () => {
      const overflowing = container.scrollWidth > container.clientWidth + EPSILON;
      const atEnd = container.scrollLeft + container.clientWidth >= container.scrollWidth - EPSILON;
      setShowBookFade(overflowing && !atEnd);
    };

    update();
    container.addEventListener('scroll', update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(table);
    ro.observe(container);
    return () => {
      container.removeEventListener('scroll', update);
      ro.disconnect();
    };
  }, [held.length]);

  return (
    <div className="space-y-0">
    <section
      data-testid="daily-brief-workspace"
      aria-label="Daily investment brief"
      className="overflow-hidden border border-hair bg-surface"
    >
      <header data-brief-section="command" className="border-b border-hair">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hair px-5 py-3 sm:px-7">
          <div className="flex min-w-0 items-center gap-3">
            <span className="text-[10px] font-bold uppercase tracking-widest text-accent">
              Morning brief
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {liveMarks ? (
              <span
                data-testid="brief-live-marks-badge"
                className="font-mono text-[0.58rem] uppercase tracking-wider text-accent"
              >
                live marks
              </span>
            ) : null}
            {showNavContract && performanceSsot ? (
              <span
                data-testid="brief-nav-contract-badge"
                className="font-mono text-[0.58rem] uppercase tracking-wider text-ink-mute"
              >
                {navContractBadgeLabel(performanceSsot.navContract)}
              </span>
            ) : null}
            {divergenceLabel ? (
              <span
                data-testid="brief-metrics-lag-badge"
                className="font-mono text-[0.58rem] uppercase tracking-wider text-warn"
              >
                {divergenceLabel}
              </span>
            ) : null}
            <AsOfBadge date={digestDate} />
          </div>
        </div>

        <div className="grid lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="px-5 py-6 sm:px-7 sm:py-7 lg:border-r lg:border-hair">
            {/* Personal pipeline update (variant B) — one attention sentence +
                Research / Portfolio / Watch beats. Regime / run-type chrome
                stays out of this hero (#3036). */}
            <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
              Your update · {digestDate ? formatAsOf(digestDate) : 'awaiting next run'}
            </p>
            <h1 className="mt-2 max-w-4xl font-display text-2xl leading-tight text-ink sm:text-3xl xl:text-4xl">
              <ClaimLink
                href={highlight.attentionHref}
                testId="brief-attention"
                className="line-clamp-6 sm:line-clamp-none"
              >
                {highlight.attention}
              </ClaimLink>
            </h1>
            <ul
              data-testid="brief-beats"
              className="mt-5 max-w-3xl space-y-2.5"
              aria-label="Research, portfolio, and watch beats"
            >
              {highlight.beats.map((beat) => (
                <li key={beat.kind} className="grid grid-cols-[5.5rem_1fr] gap-3 text-sm leading-snug">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
                    {beat.label}
                  </span>
                  <ClaimLink
                    href={beat.href}
                    className={beat.available ? 'text-ink-soft' : 'text-ink-mute'}
                  >
                    {beat.text}
                  </ClaimLink>
                </li>
              ))}
            </ul>
          </div>

          <div className="grid grid-cols-1 divide-y divide-hair sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-1 lg:divide-x-0 lg:divide-y">
            <ClaimLink
              href={decisionHref}
              testId="brief-decision-link"
              className="block px-5 py-4 sm:px-6"
            >
              <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
                Latest decision
              </p>
              <p className="mt-1 text-lg font-semibold text-ink">{decision.label}</p>
              <p className="mt-0.5 text-xs text-ink-soft">{decision.detail}</p>
            </ClaimLink>
            <BriefPipelineHealth
              runHealth={runHealth}
              diagnostics={runDiagnostics}
              snapshotDate={digestDate}
              positionDates={positionDates}
            />
          </div>
        </div>
      </header>

      <div className="px-5 py-3 sm:px-6">
        <PortfolioTeaserSurface
          tier={tier}
          tickers={held.map((p) => p.ticker)}
        />
      </div>

      <EntitledSurface artifactClass="house_weights_nav" tier={tier}>
        <BriefCardLink
          href="/portfolio/performance"
          aria-label="Open performance tearsheet"
          data-testid="brief-scoreboard-link"
          className="border-b border-hair"
        >
          <dl
            data-brief-section="scoreboard"
            className="grid grid-cols-2 divide-y divide-hair sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0"
          >
            <Metric label="Day return" value={signedPct(returns.dailyPct)} tone={metricTone(returns.dailyPct)} note={liveMarks ? 'live marks' : returns.dailyAsOf ? `as of ${formatAsOf(returns.dailyAsOf)}` : bookDate ? formatAsOf(bookDate) : 'latest price date'} />
            <Metric label="Since inception" value={signedPct(returns.sincePct)} tone={metricTone(returns.sincePct)} note={liveMarks ? 'live marks' : returns.sinceAsOf ? `as of ${formatAsOf(returns.sinceAsOf)}` : returns.sinceDate ? `from ${formatAsOf(returns.sinceDate)}` : null} />
            <Metric label={returns.benchTicker ? `vs ${returns.benchTicker}` : 'Excess return'} value={signedPct(returns.excessPct)} tone={metricTone(returns.excessPct)} note={returns.excessAsOf ? `as of ${formatAsOf(returns.excessAsOf)}` : 'aligned return window'} />
            <Metric label="Alpha" value={signedPct(returns.alphaPct)} tone={metricTone(returns.alphaPct)} note="Jensen · needs ≥20d overlap" />
            <Metric label="Info ratio" value={returns.informationRatio == null ? '—' : returns.informationRatio.toFixed(2)} tone={metricTone(returns.informationRatio)} note="ann. active ÷ tracking error" />
            <Metric label="Invested" value={`${book.investedPct.toFixed(0)}%`} note={investedNote} />
          </dl>
        </BriefCardLink>
      </EntitledSurface>

      <section data-brief-section="monitor" className="grid border-b border-hair lg:grid-cols-2 lg:divide-x lg:divide-hair">
        <BriefCardLink
          href={digestHref}
          aria-label="Open pipeline digest"
          data-testid="brief-signals-link"
          className="px-5 py-5 sm:px-7"
        >
          <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
            What matters now
          </p>
          <h2 className="mt-0.5 text-lg font-semibold text-ink">Signals to resolve</h2>
          {actionables.length === 0 ? (
            <p className="mt-4 text-sm text-ink-mute">No actionable monitor was published.</p>
          ) : (
            <ol className="mt-4 divide-y divide-hair/70">
              {actionables.slice(0, 3).map((action, index) => (
                <li key={`${action.label}-${index}`} className="grid grid-cols-[1.5rem_1fr] gap-3 py-3 first:pt-0">
                  <span className="font-mono text-xs tabular-nums text-ink-mute">
                    {String(action.priority ?? index + 1).padStart(2, '0')}
                  </span>
                  <div>
                    <p className="text-sm font-medium leading-snug text-ink">{action.label}</p>
                    {action.rationale ? (
                      <p className="mt-1 text-xs leading-snug text-ink-soft">{action.rationale}</p>
                    ) : null}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </BriefCardLink>

        <div
          data-testid="brief-risk-thesis"
          className="px-5 py-5 sm:px-7"
        >
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
                Risk and debate
              </p>
              <h2 className="mt-0.5 text-lg font-semibold text-ink">What could break the view</h2>
            </div>
            <Link
              href={thesesHref}
              className="text-[10px] font-medium text-accent hover:underline"
              data-testid="brief-risk-thesis-link"
              aria-label="Open portfolio theses"
            >
              Open theses
            </Link>
          </div>
          <div className="mt-4 divide-y divide-hair/70 border-y border-hair">
            <div className="grid grid-cols-[5.5rem_1fr] gap-3 py-3">
              <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-warn">
                <AlertTriangle size={12} /> Risk
              </span>
              {latestRisk ? (
                <div>
                  <p className="text-sm font-medium text-ink">{latestRisk.label}</p>
                  <p className="mt-1 text-xs leading-snug text-ink-soft">
                    {latestRisk.trigger || 'No explicit trigger published.'}
                    {latestRisk.horizonHours != null ? ` · ${latestRisk.horizonHours}h` : ''}
                  </p>
                </div>
              ) : (
                <p className="text-sm text-ink-mute">No tail risk was published.</p>
              )}
            </div>
            <div className="grid grid-cols-[5.5rem_1fr] gap-3 py-3">
              <span className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
                Thesis
              </span>
              {latestThesis ? (
                <div className="flex items-start gap-2">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${statusDot(latestThesis.status ?? '')}`} />
                  <ClaimLink
                    href={thesesHref}
                    className="text-sm text-ink"
                    testId="brief-thesis-link"
                  >
                    {latestThesis.name}
                  </ClaimLink>
                </div>
              ) : (
                <p className="text-sm text-ink-mute">No active thesis was published.</p>
              )}
            </div>
            <div className="grid grid-cols-[5.5rem_1fr] gap-3 py-3">
              <span className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
                Context
              </span>
              <p className="text-sm leading-snug text-ink-soft">
                {latestContext ?? 'No additional digest context was recorded.'}
              </p>
            </div>
          </div>
        </div>
      </section>

      <EntitledSurface artifactClass="house_weights_nav" tier={tier}>
      <section data-brief-section="book" className="border-b border-hair px-5 py-5 sm:px-7">
          <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
              Book monitor
            </p>
            <h2 className="mt-0.5 text-lg font-semibold text-ink">Allocation and movers</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {performanceSsot?.marksUnstamped ? (
              <span
                data-testid="brief-marks-unstamped"
                className="font-mono text-[0.58rem] uppercase tracking-wider text-warn"
              >
                marks unstamped
              </span>
            ) : null}
            <AsOfBadge date={bookDate} />
          </div>
        </div>

        <div className="mt-4 grid border-y border-hair lg:grid-cols-[minmax(14rem,0.8fr)_minmax(0,2fr)] lg:divide-x lg:divide-hair">
          <BriefCardLink
            href="/portfolio/ledger"
            aria-label="Open portfolio ledger"
            data-testid="brief-ledger-link"
            className="px-0 py-4 lg:pr-5"
          >
            <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
              Ledger
              {digestDate ? ` · ${formatAsOf(digestDate)}` : ''}
            </p>
            {ledgerPreview.length > 0 ? (
              <ul className="mt-2 divide-y divide-hair/70" data-testid="brief-ledger-day">
                {ledgerPreview.map((event) => {
                  const delta = formatBriefWeightChange(event);
                  const reason = usablePmRationale(event.reason);
                  return (
                    <li key={`${event.date}-${event.ticker}-${event.event}`} className="py-2.5 first:pt-0">
                      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                        <span className="font-mono text-sm font-bold text-ink">{event.ticker}</span>
                        <span className="text-sm capitalize text-ink-soft">{event.event.toLowerCase()}</span>
                        {delta ? (
                          <span className="font-mono text-xs tabular-nums text-ink-mute">{delta}</span>
                        ) : null}
                      </div>
                      {reason ? (
                        <p className="mt-1 line-clamp-2 text-xs leading-snug text-ink-soft">{reason}</p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-ink-mute" data-testid="brief-ledger-empty">
                No ledger activity this session
              </p>
            )}
          </BriefCardLink>

          <div
            data-testid="brief-holdings-panel"
            className="relative py-2 lg:pl-5"
          >
            <div className="mb-1 flex items-center justify-between gap-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
                Holdings
              </p>
              <Link
                href="/portfolio"
                className="text-[10px] font-medium text-accent hover:underline"
                data-testid="brief-holdings-link"
              >
                Open book
              </Link>
            </div>
            <div ref={bookScrollRef} className="overflow-x-auto">
              {held.length === 0 ? (
                <p className="py-3 text-sm text-ink-mute">No positions held; the book is all cash.</p>
              ) : (
                <>
                  <table ref={bookTableRef} className="w-full min-w-[34rem] border-collapse text-left">
                    <thead>
                      <tr className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
                        <th className="py-2 pr-3 font-bold">Holding</th>
                        <th className="px-3 py-2 text-right font-bold">Weight</th>
                        <th className="px-3 py-2 text-right font-bold">Change</th>
                        <th className="py-2 pl-3 pr-4 text-right font-bold">Day</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-hair/70">
                      {held.slice(0, 6).map((position) => {
                        const dayTone = metricTone(position.day_change_pct ?? null);
                        const deltaTone = metricTone(position.normalizedDelta ?? null);
                        return (
                          <tr key={position.ticker} className="text-xs">
                            <td className="py-2.5 pr-3">
                              <Link
                                href={tickerDossierHref(position.ticker)}
                                className="font-mono font-bold text-ink hover:text-accent hover:underline"
                              >
                                {position.ticker}
                              </Link>
                              <span className="ml-2 text-ink-mute">{position.name}</span>
                            </td>
                            <td className="px-3 py-2.5 text-right font-mono tabular-nums text-ink">
                              {position.normalizedWeight.toFixed(1)}%
                            </td>
                            <td className={`px-3 py-2.5 text-right font-mono tabular-nums ${toneClass(deltaTone)}`}>
                              {position.normalizedDelta == null ? '—' : `${position.normalizedDelta > 0 ? '+' : ''}${position.normalizedDelta.toFixed(1)}pp`}
                            </td>
                            <td className={`py-2.5 pl-3 pr-4 text-right font-mono tabular-nums ${toneClass(dayTone)}`}>
                              {signedPct(position.day_change_pct ?? null)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {showBookFade ? (
                    <div
                      aria-hidden="true"
                      className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-surface to-transparent"
                    />
                  ) : null}
                </>
              )}
            </div>
          </div>
        </div>
      </section>
      </EntitledSurface>

      <nav aria-label="Brief drill-ins" className="grid grid-cols-2 divide-x divide-y divide-hair sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0">
        {DESTINATIONS.map(({ label, href, icon: Icon }) => (
          <Link
            key={label}
            href={href ?? digestHref}
            className="flex min-h-16 items-center justify-between gap-3 px-4 py-3 text-xs font-medium text-ink-soft transition-colors hover:bg-ink/[0.03] hover:text-ink sm:px-5"
          >
            <span>{label}</span>
            <Icon size={14} className="text-ink-mute" />
          </Link>
        ))}
      </nav>
    </section>
    </div>
  );
}
