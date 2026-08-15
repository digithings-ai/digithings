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
    <section data-brief-section="command" className="overflow-hidden border-b border-hair">
      <div className="px-5 pt-5 pb-6 sm:px-7">
        {/* Quiet regime ribbon */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className={`text-[10px] font-bold uppercase tracking-widest ${accent.label}`}>
              Regime
            </span>
            <span className="text-xs text-ink-soft truncate">{regime}</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <AsOfBadge date={asOf} />
            {runType ? (
              // Reference badge dress is already uppercase mono micro-caps —
              // the old `uppercase tracking-wider` utilities are redundant.
              <Badge variant="default">{runType}</Badge>
            ) : null}
            <Badge variant={accent.badge}>{regimeLabel}</Badge>
          </div>
        </div>

        {/* THE READ — the marquee. Date wears the shared as-of format so the
            kicker, the ribbon badge, and the NAV line all read alike (#1553). */}
        <p className="mt-4 text-[11px] font-bold uppercase tracking-widest text-ink-mute">
          Brief · {asOf ? formatAsOf(asOf) : '—'}
        </p>
        <h1 className="font-display text-3xl sm:text-4xl leading-tight tracking-tight mt-1 text-ink">
          {headline ?? regime}
        </h1>
        {confidence != null ? (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="rounded-md border border-hair px-2 py-0.5 font-mono text-[11px] tabular-nums text-ink-soft">
              {confidence.toFixed(1)} confidence
            </span>
          </div>
        ) : null}

        {/* The move — demoted to a one-line status */}
        {changeCount === 0 ? (
          <p className="mt-4 text-sm text-ink-soft">{moveStatus}</p>
        ) : (
          <details className="mt-4">
            <summary className="cursor-pointer text-sm text-ink-soft marker:text-ink-mute">
              {moveStatus}
            </summary>
            <div className="mt-3">
              <TodayActionsPanel actions={actions} rationaleByTicker={rationaleByTicker} bare />
            </div>
          </details>
        )}

        {/* NAV status line — honest for one point */}
        <div className="mt-4 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-sm tabular-nums">
          <span className="text-[11px] uppercase tracking-widest text-ink-mute">NAV</span>
          <span className="text-base font-semibold text-ink">
            {nav.index == null ? '—' : nav.index.toFixed(1)}
          </span>
          {nav.sincePct != null ? (
            <span>
              <span className={sinceColor}>{signedPct(nav.sincePct)}</span>
              <span className="text-ink-soft"> since inception</span>
              {nav.sinceDate ? (
                <span className="text-ink-mute"> ({formatAsOf(nav.sinceDate)})</span>
              ) : null}
            </span>
          ) : null}
          {nav.dailyPct != null ? (
            <span>
              <span className={dailyColor}>{signedPct(nav.dailyPct)}</span>
              <span className="text-ink-soft">
                {nav.asOfDate && asOf && nav.asOfDate !== asOf
                  ? ` on ${formatAsOf(nav.asOfDate)}`
                  : ' today'}
              </span>
            </span>
          ) : null}
          {nav.benchTicker && nav.excessPct != null ? (
            <span>
              <span className={excessColor}>{signedPct(nav.excessPct)}</span>
              <span className="text-ink-soft"> vs {nav.benchTicker}</span>
            </span>
          ) : null}
        </div>
      </div>
    </section>
  );
}
