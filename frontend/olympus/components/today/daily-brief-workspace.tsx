'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  ChartNoAxesCombined,
  GitBranch,
  Shield,
  Wallet,
} from 'lucide-react';
import type {
  ActionableItem,
  DashboardPositionEvent,
  Position,
  RebalanceAction,
  RiskItem,
} from '@/lib/types';
import { reconcileBook } from '@/lib/book-reconciliation';
import { buildPipelineHref } from '@/lib/pipeline-links';
import { AsOfBadge, formatAsOf } from '@/components/shared/as-of-badge';
import { Badge } from '@/components/ui';
import HouseIdentityBanner from '@/components/house/HouseIdentityBanner';
import { activeRebalanceActions, buildBriefHighlight } from './brief-highlight';
import type { TodayThesis } from './today-summaries';

export interface BriefRunHealth {
  status: string | null;
  runDate: string | null;
  finishedAt: string | null;
  segmentsOk: number | null;
  segmentsTotal: number | null;
  segmentsCarried: number | null;
  segmentsFailed: number | null;
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
  };
  metrics: {
    maxDrawdown: number | null;
    volatility: number | null;
  };
  investedPct: number | null;
  positions: Position[];
  actionables: ActionableItem[];
  risks: RiskItem[];
  theses: TodayThesis[];
  contextBullets: string[];
  latestEvent: DashboardPositionEvent | null;
  /** `undefined` while loading, `null` when the public health view has no row. */
  runHealth: BriefRunHealth | null | undefined;
}

type Tone = 'neutral' | 'positive' | 'negative' | 'warning';

function signedPct(value: number | null): string {
  if (value == null) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;
}

function unsignedPct(value: number | null): string {
  if (value == null) return '—';
  return `${Math.abs(value).toFixed(1)}%`;
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

function runStatus(runHealth: BriefRunHealth | null | undefined): {
  label: string;
  detail: string;
  tone: Tone;
} {
  if (runHealth === undefined) {
    return {
      label: 'Checking pipeline status',
      detail: 'Reading public run telemetry',
      tone: 'neutral',
    };
  }
  if (!runHealth) {
    return {
      label: 'Pipeline status unavailable',
      detail: 'No public run telemetry',
      tone: 'neutral',
    };
  }

  const status = (runHealth.status || '').toLowerCase();
  const failed = runHealth.segmentsFailed ?? 0;
  const carried = runHealth.segmentsCarried ?? 0;
  const segmentDetail =
    runHealth.segmentsOk != null && runHealth.segmentsTotal != null
      ? `${runHealth.segmentsOk} / ${runHealth.segmentsTotal} segments`
      : 'Segment coverage unavailable';

  if (failed > 0 || ['failed', 'error'].includes(status)) {
    return { label: 'Pipeline needs attention', detail: segmentDetail, tone: 'negative' };
  }
  if (carried > 0 || ['partial', 'degraded'].includes(status)) {
    return { label: 'Pipeline completed with carry', detail: segmentDetail, tone: 'warning' };
  }
  if (['completed', 'complete', 'success', 'succeeded', 'ok'].includes(status)) {
    return { label: 'Pipeline complete', detail: segmentDetail, tone: 'positive' };
  }
  return {
    label: status ? `Pipeline ${status}` : 'Pipeline status unavailable',
    detail: segmentDetail,
    tone: 'neutral',
  };
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
    detail: active.map((action) => `${action.action} ${action.ticker}`).join(' · '),
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

function formatWeightChange(event: DashboardPositionEvent): string | null {
  if (event.weight_pct == null || event.prev_weight_pct == null) return null;
  const delta = event.weight_pct - event.prev_weight_pct;
  return `${delta > 0 ? '+' : ''}${delta.toFixed(1)}pp`;
}

const DESTINATIONS = [
  { label: 'Digest', href: null, icon: BookOpen },
  { label: 'Pipeline', href: '/pipeline', icon: GitBranch },
  { label: 'Performance', href: '/portfolio/attribution', icon: ChartNoAxesCombined },
  { label: 'Holdings', href: '/portfolio', icon: Wallet },
  { label: 'Theses', href: '/portfolio?tab=theses', icon: Shield },
] as const;

export function DailyBriefWorkspace({
  regimeLabel,
  headline,
  digestDate,
  bookDate,
  runType,
  actions,
  rationaleByTicker,
  returns,
  metrics,
  investedPct,
  positions,
  actionables,
  risks,
  theses,
  contextBullets,
  latestEvent,
  runHealth,
}: DailyBriefWorkspaceProps) {
  // `regime` + `confidence` remain on the props contract for callers / badges
  // elsewhere; the personal hero no longer dumps them as a metrics sub-line (#3036).
  const book = reconcileBook(positions, { investedPct });
  const held = book.rows
    .filter((position) => position.ticker.toUpperCase() !== 'CASH')
    .sort((a, b) => Math.abs(b.day_change_pct ?? 0) - Math.abs(a.day_change_pct ?? 0));
  const decision = decisionSummary(actions);
  const pipeline = runStatus(runHealth);
  const highlight = buildBriefHighlight({
    headline,
    actions,
    rationaleByTicker,
    actionables,
    risks,
    contextBullets,
    latestEvent,
  });
  const latestThesis = theses[0] ?? null;
  const latestRisk = risks[0] ?? null;
  const latestContext = contextBullets[0] ?? null;
  const rationaleActions = decision.active.length > 0 ? decision.active : actions;
  const decisionRationale = rationaleActions
    .map((action) => rationaleByTicker[action.ticker.trim().toUpperCase()])
    .find(Boolean);
  const digestHref = buildPipelineHref({ date: digestDate, stage: 'synthesis', node: 'digest' });

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
      <HouseIdentityBanner />
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
            <AsOfBadge date={digestDate} />
            {runType ? <Badge variant="default">{runType}</Badge> : null}
            {/* Raw `regime` dropped here (full-UI-suite critique, P3): it was
                rendered twice in this header (here, and again in the sub-line
                below next to confidence) plus once more as this styled Badge
                -- three renderings of one signal. The sub-line keeps the raw
                string paired with confidence; the command bar keeps only the
                styled, tone-colored read. */}
            <Badge variant={regimeLabel === 'bearish' || regimeLabel === 'caution' ? 'amber' : 'default'}>
              {regimeLabel}
            </Badge>
          </div>
        </div>

        <div className="grid lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="px-5 py-6 sm:px-7 sm:py-7 lg:border-r lg:border-hair">
            {/* Personal pipeline update (variant B) — one attention sentence +
                Research / Portfolio / Watch beats. Regime string + confidence
                stay on the command-bar badge only; raw levels/indicators are
                deliberately out of this hero (#3036). */}
            <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
              Your update · {digestDate ? formatAsOf(digestDate) : 'awaiting next run'}
            </p>
            <h1
              data-testid="brief-attention"
              className="mt-2 line-clamp-6 max-w-4xl font-display text-2xl leading-tight text-ink sm:line-clamp-none sm:text-3xl xl:text-4xl"
            >
              {highlight.attention}
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
                  <span className={beat.available ? 'text-ink-soft' : 'text-ink-mute'}>
                    {beat.text}
                  </span>
                </li>
              ))}
            </ul>
            <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-ink-soft">
              <Link href={digestHref} className="font-medium text-accent hover:underline sm:hidden">
                Open digest →
              </Link>
            </div>
          </div>

          <div className="grid grid-cols-1 divide-y divide-hair sm:grid-cols-2 sm:divide-x sm:divide-y-0 lg:grid-cols-1 lg:divide-x-0 lg:divide-y">
            <div className="px-5 py-4 sm:px-6">
              <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
                Latest decision
              </p>
              <p className="mt-1 text-lg font-semibold text-ink">{decision.label}</p>
              <p className="mt-0.5 text-xs text-ink-soft">{decision.detail}</p>
              {decisionRationale ? (
                <p className="mt-2 line-clamp-2 text-xs leading-snug text-ink-mute">
                  {decisionRationale}
                </p>
              ) : null}
            </div>
            <Link
              href="/pipeline"
              className="group px-5 py-4 transition-colors hover:bg-ink/[0.03] sm:px-6"
            >
              <div className="flex items-center justify-between gap-3">
                {/* "Pipeline health", not "System state" (full-UI-suite
                    critique, P1): the sidebar's own nav (lib/nav.ts) pairs
                    the label "System" with this exact Activity icon and
                    points it at /system -- a different section. This tile
                    links to /pipeline, so it now reuses GitBranch, the same
                    icon this file's own footer link already uses for
                    Pipeline (line ~192), instead of colliding with a label
                    and icon users have learned means somewhere else. */}
                <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
                  Pipeline health
                </p>
                <GitBranch size={14} className={toneClass(pipeline.tone)} />
              </div>
              <p className={`mt-1 text-sm font-semibold ${toneClass(pipeline.tone)}`}>
                {pipeline.label}
              </p>
              <p className="mt-0.5 font-mono text-[10px] tabular-nums text-ink-mute">
                {pipeline.detail}
              </p>
            </Link>
          </div>
        </div>
      </header>

      <dl
        data-brief-section="scoreboard"
        className="grid grid-cols-2 divide-y divide-hair border-b border-hair sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0"
      >
        <Metric label="Day return" value={signedPct(returns.dailyPct)} tone={metricTone(returns.dailyPct)} note={returns.dailyAsOf ? `as of ${formatAsOf(returns.dailyAsOf)}` : bookDate ? formatAsOf(bookDate) : 'latest price date'} />
        <Metric label="Since inception" value={signedPct(returns.sincePct)} tone={metricTone(returns.sincePct)} note={returns.sinceAsOf ? `as of ${formatAsOf(returns.sinceAsOf)}` : returns.sinceDate ? `from ${formatAsOf(returns.sinceDate)}` : null} />
        <Metric label={returns.benchTicker ? `vs ${returns.benchTicker}` : 'Excess return'} value={signedPct(returns.excessPct)} tone={metricTone(returns.excessPct)} note={returns.excessAsOf ? `as of ${formatAsOf(returns.excessAsOf)}` : 'aligned return window'} />
        <Metric label="Max drawdown" value={signedPct(metrics.maxDrawdown)} tone={metrics.maxDrawdown == null ? 'neutral' : 'negative'} />
        <Metric label="Volatility" value={unsignedPct(metrics.volatility)} />
        <Metric label="Invested" value={`${book.investedPct.toFixed(0)}%`} note={`${book.cashPct.toFixed(0)}% cash`} />
      </dl>

      <section data-brief-section="monitor" className="grid border-b border-hair lg:grid-cols-2 lg:divide-x lg:divide-hair">
        <div className="px-5 py-5 sm:px-7">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
                What matters now
              </p>
              <h2 className="mt-0.5 text-lg font-semibold text-ink">Signals to resolve</h2>
            </div>
            <Link href={digestHref} className="text-[10px] font-medium text-accent hover:underline">
              Full digest →
            </Link>
          </div>
          {actionables.length === 0 ? (
            <p className="text-sm text-ink-mute">No actionable monitor was published.</p>
          ) : (
            <ol className="divide-y divide-hair/70">
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
        </div>

        <div className="px-5 py-5 sm:px-7">
          <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
            Risk and debate
          </p>
          <h2 className="mt-0.5 text-lg font-semibold text-ink">What could break the view</h2>
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
                  <p className="text-sm text-ink">{latestThesis.name}</p>
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

      <section data-brief-section="book" className="border-b border-hair px-5 py-5 sm:px-7">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
              Book monitor
            </p>
            <h2 className="mt-0.5 text-lg font-semibold text-ink">Allocation and movers</h2>
          </div>
          <div className="flex items-center gap-3">
            <AsOfBadge date={bookDate} />
            <Link href="/portfolio" className="text-[10px] font-medium text-accent hover:underline">
              All holdings →
            </Link>
          </div>
        </div>

        <div className="mt-4 grid border-y border-hair lg:grid-cols-[minmax(14rem,0.8fr)_minmax(0,2fr)] lg:divide-x lg:divide-hair">
          <div className="px-0 py-4 lg:pr-5">
            <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
              Last recorded book event
            </p>
            {latestEvent ? (
              <div className="mt-2">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="font-mono text-sm font-bold text-ink">{latestEvent.ticker}</span>
                  <span className="text-sm capitalize text-ink-soft">{latestEvent.event}</span>
                  {formatWeightChange(latestEvent) ? (
                    <span className="font-mono text-xs tabular-nums text-ink-mute">
                      {formatWeightChange(latestEvent)}
                    </span>
                  ) : null}
                </div>
                <p className="mt-2 text-xs leading-snug text-ink-soft">
                  {latestEvent.reason || 'No decision rationale was recorded.'}
                </p>
                <p className="mt-2 font-mono text-[10px] text-ink-mute">
                  {formatAsOf(latestEvent.date)}
                </p>
              </div>
            ) : (
              <p className="mt-2 text-sm text-ink-mute">No book decision recorded.</p>
            )}
          </div>

          <div ref={bookScrollRef} className="relative overflow-x-auto py-2 lg:pl-5">
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
                      {/* pr-4, not pl-3 alone (CodeRabbit, PR #2287): the fade
                          below sits flush against this column's own right
                          edge, so its values need clearance to stay legible
                          under it rather than running all the way to the
                          most-opaque part of the gradient. */}
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
                            <span className="font-mono font-bold text-ink">{position.ticker}</span>
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
                {/* Scroll-edge cue (full-UI-suite critique, P2; refined per
                    CodeRabbit on PR #2287): the table's min-w-[34rem] (544px)
                    forces horizontal scroll on any viewport under ~560px --
                    every phone -- with nothing previously signaling the
                    Change/Day columns run off-screen. Shown only while
                    showBookFade is true (genuinely overflowing AND not
                    already scrolled to the end, tracked above), so it never
                    sits over content once there is nothing left to reveal --
                    and the Day column's own pr-4 keeps its values clear of
                    the fade's most-opaque edge on the trip there. */}
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
      </section>

      <nav aria-label="Brief drill-ins" className="grid grid-cols-2 divide-x divide-y divide-hair sm:grid-cols-5 sm:divide-y-0">
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