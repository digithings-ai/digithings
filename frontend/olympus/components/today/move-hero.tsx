'use client';

import type { RebalanceAction } from '@/lib/types';
import { Badge } from '@/components/ui';
import { AsOfBadge, formatAsOf } from '@/components/shared/as-of-badge';
import { TodayActionsPanel } from '@/components/overview/today-actions-panel';

/**
 * The move-led hero — the single full-weight element of the Brief (landing) page.
 *
 * Quiet regime ribbon → "Brief" (display serif) + the move (reusing the tested
 * TodayActionsPanel, which already renders the empty and all-HOLD states) → a
 * one-line NAV status. The regime accent is localized here ONLY; the page no
 * longer washes regime colour across the whole viewport.
 */

type RegimeAccent = {
  label: string;
  badge: 'default' | 'amber' | 'blue';
};

const REGIME_ACCENT: Record<string, RegimeAccent> = {
  strong_bullish: {
    label: 'text-accent',
    badge: 'blue',
  },
  bullish: {
    label: 'text-accent',
    badge: 'blue',
  },
  bearish: {
    label: 'text-warn',
    badge: 'amber',
  },
  strong_bearish: {
    label: 'text-warn',
    badge: 'amber',
  },
  caution: {
    label: 'text-warn',
    badge: 'amber',
  },
  mixed: {
    label: 'text-warn',
    badge: 'amber',
  },
  neutral: {
    label: 'text-ink-soft',
    badge: 'default',
  },
};

export interface MoveHeroNav {
  index: number | null;
  sincePct: number | null;
  sinceDate: string | null;
  dailyPct: number | null;
  benchTicker: string | null;
  excessPct: number | null;
  /**
   * Date of the latest nav_history point. When it lags the digest date the
   * daily delta must NOT read "today" — the book can freeze while research
   * stays fresh (#1555: Hermes committed nothing for 3 weeks and the hero
   * kept presenting a June NAV move as today's).
   */
  asOfDate?: string | null;
}

export interface MoveHeroProps {
  regime: string;
  regimeLabel: string;
  headline: string | null;
  confidence: number | null;
  asOf: string | null;
  runType: string | null;
  actions: RebalanceAction[];
  rationaleByTicker?: Record<string, string>;
  nav: MoveHeroNav;
}

function signedPct(v: number | null, suffix = ''): string {
  if (v == null) return '—';
  return `${v > 0 ? '+' : ''}${v.toFixed(1)}%${suffix}`;
}

export function MoveHero({
  regime,
  regimeLabel,
  headline,
  confidence,
  asOf,
  runType,
  actions,
  rationaleByTicker,
  nav,
}: MoveHeroProps) {
  const accent = REGIME_ACCENT[regimeLabel] ?? REGIME_ACCENT.neutral;
  const changeCount = actions.filter((a) => {
    const k = (a.action || '').trim().toUpperCase();
    return k !== 'HOLD' && !(k === 'EXIT' && (a.current_pct ?? 0) === 0);
  }).length;
  const moveStatus =
    changeCount === 0
      ? 'No rebalance today — holding the book'
      : `${changeCount} change${changeCount === 1 ? '' : 's'} today`;
  const sinceColor =
    nav.sincePct == null ? 'text-ink-mute' : nav.sincePct >= 0 ? 'text-up' : 'text-down';
  const dailyColor =
    nav.dailyPct == null ? 'text-ink-mute' : nav.dailyPct >= 0 ? 'text-up' : 'text-down';
  const excessColor =
    nav.excessPct == null ? 'text-ink-mute' : nav.excessPct >= 0 ? 'text-up' : 'text-down';

  return (
    <section
      data-brief-section="command"
      className="overflow-hidden border border-hair bg-surface"
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-hair px-5 py-4 sm:px-6">
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase text-ink-mute">{'// daily brief'}</p>
          <p className={`mt-1 truncate text-xs font-medium ${accent.label}`}>{regime}</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <AsOfBadge date={asOf} />
          {runType ? <Badge variant="default">{runType}</Badge> : null}
          <Badge variant={accent.badge}>{regimeLabel}</Badge>
        </div>
      </header>

      <div className="px-5 py-5 sm:px-6 sm:py-6">
        <p className="font-mono text-[10px] uppercase text-ink-mute">
          Investment command · {asOf ? formatAsOf(asOf) : '—'}
        </p>
        <h1 className="mt-2 max-w-5xl font-display text-2xl leading-tight text-ink sm:text-3xl">
          {headline ?? regime}
        </h1>

        <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-ink-soft">
          {changeCount === 0 ? (
            <span>{moveStatus}</span>
          ) : (
            <details>
              <summary className="cursor-pointer marker:text-ink-mute">{moveStatus}</summary>
              <div className="mt-3">
                <TodayActionsPanel actions={actions} rationaleByTicker={rationaleByTicker} bare />
              </div>
            </details>
          )}
          {confidence != null ? (
            <span className="border-l border-hair pl-3 font-mono text-[11px] tabular-nums text-ink-mute">
              {confidence.toFixed(1)} confidence
            </span>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-2 border-t border-hair md:grid-cols-4">
        <div className="border-b border-r border-hair px-5 py-4 md:border-b-0 sm:px-6">
          <p className="font-mono text-[10px] uppercase text-ink-mute">NAV</p>
          <p className="mt-1 font-mono text-xl font-semibold tabular-nums text-ink">
            {nav.index == null ? '—' : nav.index.toFixed(1)}
          </p>
          <p className="mt-1 text-[11px] text-ink-mute">
            {nav.asOfDate ? formatAsOf(nav.asOfDate) : 'No observation'}
          </p>
        </div>
        <div className="border-b border-hair px-5 py-4 md:border-b-0 md:border-r sm:px-6">
          <p className="font-mono text-[10px] uppercase text-ink-mute">Portfolio return</p>
          <p className={`mt-1 font-mono text-xl font-semibold tabular-nums ${sinceColor}`}>
            {signedPct(nav.sincePct)}
          </p>
          <p className="mt-1 text-[11px] text-ink-mute">
            since inception{nav.sinceDate ? ` · ${formatAsOf(nav.sinceDate)}` : ''}
          </p>
        </div>
        <div className="border-r border-hair px-5 py-4 sm:px-6">
          <p className="font-mono text-[10px] uppercase text-ink-mute">Latest session</p>
          <p className={`mt-1 font-mono text-xl font-semibold tabular-nums ${dailyColor}`}>
            {signedPct(nav.dailyPct)}
          </p>
          <p className="mt-1 text-[11px] text-ink-mute">
            {nav.dailyPct == null
              ? 'No second observation'
              : nav.asOfDate && asOf && nav.asOfDate !== asOf
                ? `on ${formatAsOf(nav.asOfDate)}`
                : 'today'}
          </p>
        </div>
        <div className="px-5 py-4 sm:px-6">
          <p className="font-mono text-[10px] uppercase text-ink-mute">Active return</p>
          <p className={`mt-1 font-mono text-xl font-semibold tabular-nums ${excessColor}`}>
            {signedPct(nav.excessPct)}
          </p>
          <p className="mt-1 text-[11px] text-ink-mute">
            {nav.benchTicker ? `Versus ${nav.benchTicker}` : 'No benchmark'}
          </p>
        </div>
      </div>
    </section>
  );
}
