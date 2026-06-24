'use client';

import type { RebalanceAction } from '@/lib/types';
import { Badge } from '@/components/ui';
import { AsOfBadge } from '@/components/overview/as-of-badge';
import { TodayActionsPanel } from '@/components/overview/today-actions-panel';

/**
 * The move-led hero — the single full-weight element of the Today page.
 *
 * Quiet regime ribbon → "Today" (display serif) + the move (reusing the tested
 * TodayActionsPanel, which already renders the empty and all-HOLD states) → a
 * one-line NAV status. The regime accent is localized here ONLY; the page no
 * longer washes regime colour across the whole viewport.
 */

type RegimeAccent = {
  border: string;
  bg: string;
  label: string;
  badge: 'green' | 'red' | 'amber' | 'blue';
};

const REGIME_ACCENT: Record<string, RegimeAccent> = {
  strong_bullish: {
    border: 'border-fin-green/60',
    bg: 'bg-gradient-to-br from-fin-green/[0.10] via-transparent to-transparent',
    label: 'text-fin-green',
    badge: 'green',
  },
  bullish: {
    border: 'border-fin-green/45',
    bg: 'bg-gradient-to-br from-fin-green/[0.07] via-transparent to-transparent',
    label: 'text-fin-green',
    badge: 'green',
  },
  bearish: {
    border: 'border-fin-red/45',
    bg: 'bg-gradient-to-br from-fin-red/[0.07] via-transparent to-transparent',
    label: 'text-fin-red',
    badge: 'red',
  },
  strong_bearish: {
    border: 'border-fin-red/60',
    bg: 'bg-gradient-to-br from-fin-red/[0.10] via-transparent to-transparent',
    label: 'text-fin-red',
    badge: 'red',
  },
  caution: {
    border: 'border-fin-amber/50',
    bg: 'bg-gradient-to-br from-fin-amber/[0.07] via-transparent to-transparent',
    label: 'text-fin-amber',
    badge: 'amber',
  },
  mixed: {
    border: 'border-fin-amber/40',
    bg: 'bg-gradient-to-br from-fin-amber/[0.05] via-transparent to-transparent',
    label: 'text-fin-amber',
    badge: 'amber',
  },
  neutral: {
    border: 'border-fin-blue/40',
    bg: 'bg-gradient-to-br from-fin-blue/[0.06] via-transparent to-transparent',
    label: 'text-fin-blue',
    badge: 'blue',
  },
};

export interface MoveHeroNav {
  index: number | null;
  sincePct: number | null;
  sinceDate: string | null;
  dailyPct: number | null;
  benchTicker: string | null;
  excessPct: number | null;
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
    nav.sincePct == null ? 'text-text-muted' : nav.sincePct >= 0 ? 'text-fin-green' : 'text-fin-red';
  const dailyColor =
    nav.dailyPct == null ? 'text-text-muted' : nav.dailyPct >= 0 ? 'text-fin-green' : 'text-fin-red';
  const excessColor =
    nav.excessPct == null ? 'text-text-muted' : nav.excessPct >= 0 ? 'text-fin-green' : 'text-fin-red';

  return (
    <section className={`glass-card border ${accent.border} ${accent.bg} overflow-hidden`}>
      <div className="px-5 pt-5 pb-6 sm:px-7">
        {/* Quiet regime ribbon */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className={`text-[10px] font-bold uppercase tracking-widest ${accent.label}`}>
              Regime
            </span>
            <span className="text-xs text-text-secondary truncate">{regime}</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <AsOfBadge date={asOf} />
            {runType ? (
              <Badge variant="default" className="uppercase tracking-wider">
                {runType}
              </Badge>
            ) : null}
            <Badge variant={accent.badge}>{regimeLabel}</Badge>
          </div>
        </div>

        {/* THE READ — the marquee */}
        <p className="mt-4 text-[11px] font-bold uppercase tracking-widest text-text-muted">
          Today · {asOf ?? '—'}
        </p>
        <h1 className="font-display text-3xl sm:text-4xl leading-tight tracking-tight mt-1 text-text-primary">
          {headline ?? regime}
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {confidence != null ? (
            <span className="rounded-md border border-border-subtle px-2 py-0.5 font-mono text-[11px] tabular-nums text-text-secondary">
              {confidence.toFixed(1)} confidence
            </span>
          ) : null}
          <span className="text-xs text-text-secondary">{regime}</span>
        </div>

        {/* The move — demoted to a one-line status */}
        {changeCount === 0 ? (
          <p className="mt-4 text-sm text-text-secondary">{moveStatus}</p>
        ) : (
          <details className="mt-4">
            <summary className="cursor-pointer text-sm text-text-secondary marker:text-text-muted">
              {moveStatus}
            </summary>
            <div className="mt-3">
              <TodayActionsPanel actions={actions} rationaleByTicker={rationaleByTicker} bare />
            </div>
          </details>
        )}

        {/* NAV status line — honest for one point */}
        <div className="mt-4 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-sm tabular-nums">
          <span className="text-[11px] uppercase tracking-widest text-text-muted">NAV</span>
          <span className="text-base font-semibold text-text-primary">
            {nav.index == null ? '—' : nav.index.toFixed(1)}
          </span>
          {nav.sincePct != null ? (
            <span className={sinceColor}>
              {signedPct(nav.sincePct)} since inception
              {nav.sinceDate ? <span className="text-text-muted"> ({nav.sinceDate})</span> : null}
            </span>
          ) : null}
          {nav.dailyPct != null ? (
            <span className={dailyColor}>{signedPct(nav.dailyPct, ' today')}</span>
          ) : null}
          {nav.benchTicker && nav.excessPct != null ? (
            <span className={excessColor}>
              {signedPct(nav.excessPct)} vs {nav.benchTicker}
            </span>
          ) : null}
        </div>
      </div>
    </section>
  );
}
