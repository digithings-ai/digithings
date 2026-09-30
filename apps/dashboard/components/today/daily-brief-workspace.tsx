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
import {
  Badge,
  CompositionBar,
  Donut,
  DivergingBars,
  EmptyState,
  ScoreBar,
  SegmentedControl,
  Sparkline,
  Stat,
  StatusDot,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@digithings/ui/ui';
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
import {
  BRIEF_RANGES,
  compositionSegments,
  clipToRun,
  excessSeries,
  ledgerEventTone,
  moverItems,
  navSparkValues,
  rebalanceBullets,
  seriesStats,
  signedPctText,
  sparkValues,
  thesisStatusTone,
  trendTone,
  windowNavPoints,
  type BenchmarkPricePoint,
  type BriefNavPoint,
  type BriefRange,
} from '@/lib/brief-visuals';
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

function PanelLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">{children}</p>
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
  /**
   * Persisted `/performance` NAV points (base 100). Feeds the KPI sparklines
   * and hero chart; never the live-marks overlay. Empty → em-dash states.
   */
  navPoints?: BriefNavPoint[];
  /** Benchmark closes for `returns.benchTicker` (excess sparkline, fail-closed). */
  benchmarkHistory?: BenchmarkPricePoint[] | null;
}

type Tone = 'neutral' | 'positive' | 'negative' | 'warning';

function signedPct(value: number | null): string {
  return signedPctText(value);
}

function metricTone(value: number | null): Tone {
  if (value == null || value === 0) return 'neutral';
  return value > 0 ? 'positive' : 'negative';
}

/** up/down are P&L colours only — every caller here passes a return / P&L value. */
function toneClass(tone: Tone): string {
  if (tone === 'positive') return 'text-up';
  if (tone === 'negative') return 'text-down';
  if (tone === 'warning') return 'text-warn';
  return 'text-ink';
}

/** Coloured KPI value; `null` lets `Stat` render its em dash. */
function kpiValue(text: string | null, tone: Tone): ReactNode {
  if (text == null) return null;
  return <span className={toneClass(tone)}>{text}</span>;
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

const DESTINATIONS = [
  { label: 'Digest', href: null as string | null, icon: BookOpen },
  { label: 'Pipeline', href: '/pipeline', icon: GitBranch },
  { label: 'Performance', href: '/portfolio/performance', icon: ChartNoAxesCombined },
  { label: 'Holdings', href: '/portfolio', icon: Wallet },
  { label: 'Ledger', href: '/portfolio/ledger', icon: ListOrdered },
  { label: 'Theses', href: '/portfolio?tab=theses', icon: Shield },
] as const;

const LEDGER_DAY_PREVIEW = 4;
const KPI_SPARK_POINTS = 60;
const RANGE_LABELS: Record<BriefRange, string> = { '1M': '1M', '3M': '3M', ALL: 'All' };

const pctFormat = (v: number) => `${Math.round(v * 100)}%`;

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
  navPoints = [],
  benchmarkHistory = null,
}: DailyBriefWorkspaceProps) {
  // `regime`, `regimeLabel`, `confidence`, `runType` and `metrics` remain on the
  // props contract for callers; the Brief header keeps only the as-of date — no
  // decorative run-type / tone pills (#3036 follow-up). Drawdown is derived from
  // the persisted NAV series below, so the unverified-unit `metrics` stay unused.
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
  const investedDisplay =
    investedPct != null && Number.isFinite(investedPct) ? investedPct : book.investedPct;

  // ── Visual series (pure helpers in lib/brief-visuals) ─────────────────────
  const [range, setRange] = useState<BriefRange>('ALL');
  const navWindow = windowNavPoints(navPoints, range);
  const navValues = navWindow.map((p) => p.index);
  const navStats = seriesStats(navValues);
  // Excess is rebased on the current NAV run (same start as the headline), so
  // the series never spans the legacy→finalized seam (#3935).
  const runNav = clipToRun(navPoints, returns.sinceDate);
  const heroExcess = excessSeries(windowNavPoints(runNav, range), benchmarkHistory);
  const daySpark = navSparkValues(navPoints, 30);
  const sinceSpark = navSparkValues(navPoints, KPI_SPARK_POINTS);
  const excessSpark = sparkValues(excessSeries(runNav, benchmarkHistory), KPI_SPARK_POINTS);
  const sparkNote = liveMarks ? 'Persisted NAV trend (live marks not charted)' : 'NAV trend';
  const compSegments = compositionSegments(held, cashForNote);
  const movers = moverItems(held, 6);
  const bullets = rebalanceBullets(actions);
  const investedBar = Math.min(100, Math.max(0, investedDisplay));

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
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hair px-4 py-2 sm:px-5">
          <span className="text-[10px] font-bold uppercase tracking-widest text-accent">
            Morning brief
          </span>
          <div className="flex flex-wrap items-center gap-2">
            {liveMarks ? (
              <Badge variant="accent" data-testid="brief-live-marks-badge" className="font-mono text-[0.58rem] uppercase tracking-wider">
                live marks
              </Badge>
            ) : null}
            {showNavContract && performanceSsot ? (
              <Badge variant="neutral" data-testid="brief-nav-contract-badge" className="font-mono text-[0.58rem] uppercase tracking-wider">
                {navContractBadgeLabel(performanceSsot.navContract)}
              </Badge>
            ) : null}
            {divergenceLabel ? (
              <Badge variant="warn" data-testid="brief-metrics-lag-badge" className="font-mono text-[0.58rem] uppercase tracking-wider">
                {divergenceLabel}
              </Badge>
            ) : null}
            <AsOfBadge date={digestDate} />
          </div>
        </div>

        <div className="grid lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="px-4 py-4 sm:px-5 lg:border-r lg:border-hair">
            {/* Personal pipeline update (variant B) — one attention sentence +
                Research / Portfolio / Watch beats. Regime / run-type chrome
                stays out of this hero (#3036). */}
            <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
              Your update · {digestDate ? formatAsOf(digestDate) : 'awaiting next run'}
            </p>
            <h1 className="mt-1.5 max-w-4xl font-display text-xl leading-tight text-ink sm:text-2xl">
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
              className="mt-3 max-w-3xl space-y-1.5"
              aria-label="Research, portfolio, and watch beats"
            >
              {highlight.beats.map((beat) => (
                <li key={beat.kind} className="grid grid-cols-[5rem_1fr] gap-3 text-sm leading-snug">
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
              className="block px-4 py-3 sm:px-5"
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

      <div className="px-4 py-2 sm:px-5">
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
          <div
            data-brief-section="scoreboard"
            className="grid grid-cols-1 gap-px bg-hair sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6"
          >
            <Stat
              className="border-0"
              label="Day return"
              value={kpiValue(returns.dailyPct == null ? null : signedPct(returns.dailyPct), metricTone(returns.dailyPct))}
              hint={liveMarks ? 'live marks' : returns.dailyAsOf ? `as of ${formatAsOf(returns.dailyAsOf)}` : bookDate ? formatAsOf(bookDate) : 'latest price date'}
              spark={daySpark.length > 0 ? <Sparkline values={daySpark} tone={trendTone(daySpark)} label={sparkNote} width={64} /> : undefined}
            />
            <Stat
              className="border-0"
              label="Since inception"
              value={kpiValue(returns.sincePct == null ? null : signedPct(returns.sincePct), metricTone(returns.sincePct))}
              hint={liveMarks ? 'live marks' : returns.sinceAsOf ? `as of ${formatAsOf(returns.sinceAsOf)}` : returns.sinceDate ? `from ${formatAsOf(returns.sinceDate)}` : null}
              spark={sinceSpark.length > 0 ? <Sparkline values={sinceSpark} tone={trendTone(sinceSpark)} area label={sparkNote} width={64} /> : undefined}
            />
            <Stat
              className="border-0"
              label={returns.benchTicker ? `vs ${returns.benchTicker}` : 'Excess return'}
              value={kpiValue(returns.excessPct == null ? null : signedPct(returns.excessPct), metricTone(returns.excessPct))}
              hint={returns.excessAsOf ? `as of ${formatAsOf(returns.excessAsOf)}` : 'aligned return window'}
              spark={excessSpark.length > 0 ? <Sparkline values={excessSpark} tone={trendTone(excessSpark)} label="Relative return vs benchmark" width={64} /> : undefined}
            />
            <Stat
              className="border-0"
              label="Alpha"
              value={kpiValue(returns.alphaPct == null ? null : signedPct(returns.alphaPct), metricTone(returns.alphaPct))}
              hint="Jensen · needs ≥20d overlap"
            />
            <Stat
              className="border-0"
              label="Info ratio"
              value={kpiValue(returns.informationRatio == null ? null : returns.informationRatio.toFixed(2), metricTone(returns.informationRatio))}
              hint="ann. active ÷ tracking error"
            />
            <Stat
              className="border-0"
              label="Invested"
              value={`${investedDisplay.toFixed(0)}%`}
              hint={investedNote}
              spark={
                <CompositionBar
                  className="w-16"
                  mode="stacked"
                  total={100}
                  height={6}
                  label={`Invested versus cash: ${investedNote}`}
                  segments={[
                    { key: 'invested', label: 'Invested', value: investedBar, tone: 'accent' },
                    { key: 'cash', label: 'Cash', value: Math.min(Math.max(0, cashForNote), 100 - investedBar), cash: true },
                  ]}
                />
              }
            />
          </div>
        </BriefCardLink>

        <section
          data-brief-section="nav"
          className="grid border-b border-hair lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] lg:divide-x lg:divide-hair"
        >
          <div className="px-4 py-3 sm:px-5" data-testid="brief-nav-chart">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <PanelLabel>Performance</PanelLabel>
                <h2 className="mt-0.5 text-sm font-semibold text-ink">NAV index, base 100</h2>
              </div>
              <SegmentedControl
                dress="accent"
                aria-label="NAV range"
                options={BRIEF_RANGES.map((r) => ({ value: r, label: RANGE_LABELS[r] }))}
                value={range}
                onChange={setRange}
              />
            </div>
            {navStats ? (
              <div className="mt-2">
                <Sparkline
                  values={navValues}
                  tone={trendTone(navValues)}
                  area
                  width={640}
                  height={120}
                  className="h-auto w-full"
                  label={`Persisted NAV index over ${navValues.length} sessions`}
                />
                {heroExcess.length > 0 ? (
                  <div className="mt-1">
                    <PanelLabel>{returns.benchTicker ? `Relative to ${returns.benchTicker}` : 'Relative to benchmark'}</PanelLabel>
                    <Sparkline
                      values={heroExcess}
                      tone="accent"
                      width={640}
                      height={36}
                      lastDot={false}
                      className="h-auto w-full"
                      label="Cumulative relative return versus benchmark"
                    />
                  </div>
                ) : null}
                <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px] tabular-nums text-ink-mute">
                  <div className="flex gap-1.5">
                    <dt>Range</dt>
                    <dd className={toneClass(metricTone(navStats.changePct))}>{signedPct(navStats.changePct)}</dd>
                  </div>
                  <div className="flex gap-1.5">
                    <dt>High</dt>
                    <dd className="text-ink">{navStats.high.toFixed(1)}</dd>
                  </div>
                  <div className="flex gap-1.5">
                    <dt>Low</dt>
                    <dd className="text-ink">{navStats.low.toFixed(1)}</dd>
                  </div>
                  <div className="flex gap-1.5">
                    <dt>Drawdown</dt>
                    <dd className="text-ink">{navStats.maxDrawdownPct.toFixed(1)}%</dd>
                  </div>
                  <div className="flex gap-1.5">
                    <dt>{navWindow[0] ? formatAsOf(navWindow[0].date) : ''}</dt>
                    <dd>→ {navWindow.length ? formatAsOf(navWindow[navWindow.length - 1].date) : ''}</dd>
                  </div>
                </dl>
              </div>
            ) : (
              <EmptyState
                className="mt-2 py-6"
                title="Not enough history"
                body="The NAV line appears once at least two accounting points are published."
              />
            )}
          </div>

          <div className="px-4 py-3 sm:px-5" data-testid="brief-composition">
            <PanelLabel>Book composition</PanelLabel>
            <h2 className="mt-0.5 text-sm font-semibold text-ink">Weights and cash</h2>
            {compSegments.length > 0 ? (
              <Donut
                className="mt-3"
                size={148}
                thickness={20}
                segments={compSegments}
                label="Book composition by weight, with cash"
              >
                <span className="font-mono text-lg font-semibold tabular-nums text-ink">
                  {investedDisplay.toFixed(0)}%
                </span>
                <span className="text-[10px] uppercase tracking-widest text-ink-mute">invested</span>
              </Donut>
            ) : (
              <p className="mt-3 text-sm text-ink-mute">No book weights to chart.</p>
            )}
          </div>
        </section>
      </EntitledSurface>

      <section data-brief-section="monitor" className="grid border-b border-hair lg:grid-cols-2 lg:divide-x lg:divide-hair">
        <BriefCardLink
          href={digestHref}
          aria-label="Open pipeline digest"
          data-testid="brief-signals-link"
          className="px-4 py-3 sm:px-5"
        >
          <PanelLabel>What matters now</PanelLabel>
          <h2 className="mt-0.5 text-sm font-semibold text-ink">Signals to resolve</h2>
          {actionables.length === 0 ? (
            <p className="mt-3 text-sm text-ink-mute">No actionable monitor was published.</p>
          ) : (
            <ol className="mt-2 divide-y divide-hair/70">
              {actionables.slice(0, 3).map((action, index) => (
                <li key={`${action.label}-${index}`} className="grid grid-cols-[1.75rem_1fr] items-baseline gap-2 py-1.5">
                  <span className="border border-hair px-1 text-center font-mono text-[10px] tabular-nums text-ink-mute">
                    {String(action.priority ?? index + 1).padStart(2, '0')}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-medium leading-snug text-ink">{action.label}</p>
                    {action.rationale ? (
                      <p className="line-clamp-1 text-xs text-ink-soft" title={action.rationale}>
                        {action.rationale}
                      </p>
                    ) : null}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </BriefCardLink>

        <div
          data-testid="brief-risk-thesis"
          className="px-4 py-3 sm:px-5"
        >
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <PanelLabel>Risk and debate</PanelLabel>
              <h2 className="mt-0.5 text-sm font-semibold text-ink">What could break the view</h2>
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
          <div className="mt-2 divide-y divide-hair/70 border-y border-hair">
            <div className="grid grid-cols-[4.5rem_1fr] items-baseline gap-3 py-1.5">
              <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-warn">
                <AlertTriangle size={12} /> Risk
              </span>
              {latestRisk ? (
                <div className="min-w-0">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="text-sm font-medium text-ink">{latestRisk.label}</p>
                    {latestRisk.horizonHours != null ? (
                      <Badge variant="warn" className="font-mono text-[0.58rem]">
                        {latestRisk.horizonHours}h
                      </Badge>
                    ) : null}
                  </div>
                  <p className="line-clamp-1 text-xs text-ink-soft" title={latestRisk.trigger || undefined}>
                    {latestRisk.trigger || 'No explicit trigger published.'}
                  </p>
                </div>
              ) : (
                <p className="text-sm text-ink-mute">No tail risk was published.</p>
              )}
            </div>
            <div className="grid grid-cols-[4.5rem_1fr] items-center gap-3 py-1.5">
              <PanelLabel>Thesis</PanelLabel>
              {latestThesis ? (
                <div className="flex min-w-0 items-center gap-2">
                  <StatusDot tone={thesisStatusTone(latestThesis.status)} label={latestThesis.status ?? 'status unknown'} />
                  <ClaimLink
                    href={thesesHref}
                    className="min-w-0 truncate text-sm text-ink"
                    testId="brief-thesis-link"
                  >
                    {latestThesis.name}
                  </ClaimLink>
                  {typeof latestThesis.confidence === 'number' ? (
                    <ScoreBar
                      className="ml-auto w-16"
                      min={0}
                      max={1}
                      value={latestThesis.confidence}
                      tone="accent"
                      format={pctFormat}
                      label="Thesis confidence"
                    />
                  ) : null}
                </div>
              ) : (
                <p className="text-sm text-ink-mute">No active thesis was published.</p>
              )}
            </div>
            <div className="grid grid-cols-[4.5rem_1fr] items-baseline gap-3 py-1.5">
              <PanelLabel>Context</PanelLabel>
              <p className="line-clamp-2 text-sm leading-snug text-ink-soft" title={latestContext ?? undefined}>
                {latestContext ?? 'No additional digest context was recorded.'}
              </p>
            </div>
          </div>
        </div>
      </section>

      <EntitledSurface artifactClass="house_weights_nav" tier={tier}>
      <section data-brief-section="book" className="border-b border-hair px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <PanelLabel>Book monitor</PanelLabel>
            <h2 className="mt-0.5 text-sm font-semibold text-ink">Allocation and movers</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {performanceSsot?.marksUnstamped ? (
              <Badge variant="warn" data-testid="brief-marks-unstamped" className="font-mono text-[0.58rem] uppercase tracking-wider">
                marks unstamped
              </Badge>
            ) : null}
            <AsOfBadge date={bookDate} />
          </div>
        </div>

        <div className="mt-3 grid border-y border-hair lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1fr)] lg:divide-x lg:divide-hair">
          <div
            data-testid="brief-holdings-panel"
            className="relative py-3 lg:pr-4"
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <PanelLabel>Holdings</PanelLabel>
              <Link
                href="/portfolio"
                className="text-[10px] font-medium text-accent hover:underline"
                data-testid="brief-holdings-link"
              >
                Open book
              </Link>
            </div>
            {held.length === 0 ? (
              <p className="py-3 text-sm text-ink-mute">No positions held; the book is all cash.</p>
            ) : (
              <>
                {movers.length > 0 ? (
                  <DivergingBars
                    data-testid="brief-movers"
                    items={movers}
                    label="Day change by holding"
                    format={(v) => signedPct(v)}
                    className="mb-3"
                  />
                ) : null}
                <div ref={bookScrollRef} className="overflow-x-auto [&>div]:overflow-visible">
                  <Table ref={bookTableRef} className="min-w-[20rem] border-collapse text-left">
                    <TableHeader>
                      <TableRow className="text-[10px] font-bold uppercase tracking-widest text-ink-mute hover:bg-transparent">
                        <TableHead className="h-auto py-1.5 pr-3 font-bold">Holding</TableHead>
                        <TableHead numeric className="h-auto px-3 py-1.5 font-bold">Weight</TableHead>
                        <TableHead numeric className="h-auto py-1.5 pl-3 font-bold">Change</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody className="divide-y divide-hair/70">
                      {held.slice(0, 6).map((position) => {
                        const deltaTone = metricTone(position.normalizedDelta ?? null);
                        return (
                          <TableRow key={position.ticker} className="border-0 text-xs hover:bg-transparent">
                            <TableCell className="py-1.5 pr-3 whitespace-normal">
                              <Link
                                href={tickerDossierHref(position.ticker)}
                                className="font-mono font-bold text-ink hover:text-accent hover:underline"
                              >
                                {position.ticker}
                              </Link>
                              <span className="ml-2 text-ink-mute">{position.name}</span>
                            </TableCell>
                            <TableCell numeric className="px-3 py-1.5 font-mono text-ink">
                              {position.normalizedWeight.toFixed(1)}%
                            </TableCell>
                            <TableCell numeric className={`py-1.5 pl-3 font-mono ${toneClass(deltaTone)}`}>
                              {position.normalizedDelta == null ? '—' : `${position.normalizedDelta > 0 ? '+' : ''}${position.normalizedDelta.toFixed(1)}pp`}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
                {showBookFade ? (
                  <div
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-surface to-transparent"
                  />
                ) : null}
              </>
            )}
          </div>

          <div data-testid="brief-rebalance" className="py-3 lg:px-4">
            <PanelLabel>Sizing decisions</PanelLabel>
            {bullets.length > 0 ? (
              <ul className="mt-2 space-y-2">
                {bullets.slice(0, 6).map((b) => (
                  <li key={b.ticker} className="grid grid-cols-[3.5rem_minmax(0,1fr)] items-center gap-2 text-xs">
                    <Link
                      href={tickerDossierHref(b.ticker)}
                      className="font-mono font-bold text-ink hover:text-accent hover:underline"
                    >
                      {b.ticker}
                    </Link>
                    <div className="min-w-0">
                      <div className="flex items-baseline justify-between gap-2 font-mono tabular-nums">
                        <span className="text-ink-soft">{b.verb}</span>
                        <span className="text-ink-mute">{b.text}</span>
                      </div>
                      <ScoreBar
                        min={0}
                        max={b.axisMax}
                        origin={b.current}
                        value={b.recommended}
                        tone={b.tone}
                        ticks={[{ value: b.current, label: 'Current weight', tone: 'mute' }]}
                        format={(v) => `${v.toFixed(1)}%`}
                        label={`${b.ticker} recommended weight`}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-ink-mute">No weight changes to size.</p>
            )}
          </div>

          <BriefCardLink
            href="/portfolio/ledger"
            aria-label="Open portfolio ledger"
            data-testid="brief-ledger-link"
            className="py-3 lg:pl-4"
          >
            <PanelLabel>
              Ledger
              {digestDate ? ` · ${formatAsOf(digestDate)}` : ''}
            </PanelLabel>
            {ledgerPreview.length > 0 ? (
              <ul className="mt-2 divide-y divide-hair/70" data-testid="brief-ledger-day">
                {ledgerPreview.map((event) => {
                  const delta = formatBriefWeightChange(event);
                  const reason = usablePmRationale(event.reason);
                  return (
                    <li key={`${event.date}-${event.ticker}-${event.event}`} className="py-1.5 first:pt-0">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                        <StatusDot tone={ledgerEventTone(event.event)} label={event.event.toLowerCase()} />
                        <span className="font-mono text-sm font-bold text-ink">{event.ticker}</span>
                        <span className="text-sm capitalize text-ink-soft">{event.event.toLowerCase()}</span>
                        {delta ? (
                          <span className="font-mono text-xs tabular-nums text-ink-mute">{delta}</span>
                        ) : null}
                      </div>
                      {reason ? (
                        <p className="mt-0.5 line-clamp-2 text-xs leading-snug text-ink-soft" title={reason}>{reason}</p>
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
        </div>
      </section>
      </EntitledSurface>

      <nav aria-label="Brief drill-ins" className="grid grid-cols-2 divide-x divide-y divide-hair sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0">
        {DESTINATIONS.map(({ label, href, icon: Icon }) => (
          <Link
            key={label}
            href={href ?? digestHref}
            className="flex min-h-12 items-center justify-between gap-3 px-4 py-2 text-xs font-medium text-ink-soft transition-colors hover:bg-ink/[0.03] hover:text-ink sm:px-5"
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
