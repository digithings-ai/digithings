'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { ArrowRight, ArrowDownRight, ArrowUpRight, XCircle, PlusCircle, ListChecks } from 'lucide-react';
import type { RebalanceAction } from '@/lib/types';

/**
 * "What should I change today" — renders the PM's rebalance_actions (computed
 * in queries.ts but, before #702, never surfaced). The decision spine of the
 * morning read: EXIT/OPEN/TRIM/ADD sorted to the top, HOLDs collapsed.
 */

type ActionKind = 'EXIT' | 'OPEN' | 'TRIM' | 'ADD' | 'HOLD';

const ORDER: Record<ActionKind, number> = { EXIT: 0, OPEN: 1, TRIM: 2, ADD: 3, HOLD: 4 };

const STYLE: Record<ActionKind, { badge: string; icon: typeof ArrowRight }> = {
  EXIT: { badge: 'bg-fin-red/15 text-fin-red border-fin-red/30', icon: XCircle },
  OPEN: { badge: 'bg-fin-green/15 text-fin-green border-fin-green/30', icon: PlusCircle },
  TRIM: { badge: 'bg-fin-amber/15 text-fin-amber border-fin-amber/30', icon: ArrowDownRight },
  ADD: { badge: 'bg-fin-blue/15 text-fin-blue border-fin-blue/30', icon: ArrowUpRight },
  HOLD: { badge: 'bg-white/[0.06] text-text-muted border-border-subtle', icon: ArrowRight },
};

function kindOf(action: string): ActionKind {
  const a = (action || '').toUpperCase();
  return (a in ORDER ? a : 'HOLD') as ActionKind;
}

function ActionRow({ a, rationale }: { a: RebalanceAction; rationale?: string }) {
  const kind = kindOf(a.action);
  const { badge, icon: Icon } = STYLE[kind];
  const delta = (a.recommended_pct ?? 0) - (a.current_pct ?? 0);
  return (
    <div className="px-5 py-2.5 hover:bg-white/[0.025] transition-colors">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span
            className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${badge}`}
          >
            <Icon size={11} />
            {kind}
          </span>
          <span className="font-mono text-xs font-bold text-text-primary">{a.ticker}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0 font-mono text-xs tabular-nums">
          <span className="text-text-muted">{(a.current_pct ?? 0).toFixed(1)}%</span>
          <ArrowRight size={11} className="text-text-muted/60" />
          <span className="text-text-primary font-semibold">{(a.recommended_pct ?? 0).toFixed(1)}%</span>
          {Math.abs(delta) >= 0.05 && (
            <span className={delta > 0 ? 'text-fin-green' : 'text-fin-red'}>
              {delta > 0 ? '+' : ''}
              {delta.toFixed(1)}pp
            </span>
          )}
        </div>
      </div>
      {rationale && (
        <p className="mt-1 pl-1 text-[11px] leading-snug text-text-muted">{rationale}</p>
      )}
    </div>
  );
}

export function TodayActionsPanel({
  actions,
  rationaleByTicker,
}: {
  actions: RebalanceAction[];
  /** Per-ticker rationale from the PM rebalance memo (#704); the rationale line
   *  is omitted entirely for tickers with no memo entry. */
  rationaleByTicker?: Record<string, string>;
}) {
  const [showHolds, setShowHolds] = useState(false);
  const rationale = (ticker: string): string | undefined =>
    rationaleByTicker?.[ticker.trim().toUpperCase()];
  const { changes, holds } = useMemo(() => {
    const sorted = [...actions].sort((x, y) => ORDER[kindOf(x.action)] - ORDER[kindOf(y.action)]);
    return {
      changes: sorted.filter((a) => kindOf(a.action) !== 'HOLD'),
      holds: sorted.filter((a) => kindOf(a.action) === 'HOLD'),
    };
  }, [actions]);

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border-subtle bg-bg-secondary flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ListChecks size={15} className="text-fin-green" />
          <h3 className="text-sm font-semibold">Today&rsquo;s actions</h3>
          {changes.length > 0 && (
            <span className="rounded-full bg-fin-green/15 text-fin-green border border-fin-green/30 px-2 py-0.5 text-[10px] font-bold tabular-nums">
              {changes.length}
            </span>
          )}
        </div>
        <Link
          href="/portfolio?tab=analysis"
          className="text-[10px] text-fin-blue hover:underline font-medium"
        >
          Full rebalance memo →
        </Link>
      </div>

      {changes.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-text-muted">
          {actions.length === 0
            ? 'No rebalance proposed for the latest run.'
            : 'No changes proposed — portfolio is at target weights.'}
        </p>
      ) : (
        <div className="divide-y divide-border-subtle">
          {changes.map((a, i) => (
            <ActionRow key={`${a.ticker}-${i}`} a={a} rationale={rationale(a.ticker)} />
          ))}
        </div>
      )}

      {holds.length > 0 && (
        <div className="border-t border-border-subtle">
          <button
            type="button"
            onClick={() => setShowHolds((v) => !v)}
            className="w-full px-5 py-2 text-left text-[11px] text-text-muted hover:text-text-secondary transition-colors"
          >
            {showHolds ? '▾' : '▸'} {holds.length} position{holds.length !== 1 ? 's' : ''} held
          </button>
          {showHolds && (
            <div className="divide-y divide-border-subtle/60">
              {holds.map((a, i) => (
                <ActionRow key={`hold-${a.ticker}-${i}`} a={a} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
