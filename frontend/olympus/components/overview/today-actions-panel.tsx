'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { ArrowRight, ArrowDownRight, ArrowUpRight, XCircle, PlusCircle, ListChecks } from 'lucide-react';
import { EVENT_COLORS, withAlpha } from '@/lib/chart-colors';
import type { RebalanceAction } from '@/lib/types';

/**
 * "What should I change today" — renders the PM's rebalance_actions (computed
 * in queries.ts but, before #702, never surfaced). The decision spine of the
 * morning read: new/OPEN/ADD/TRIM sorted to the top, HOLDs collapsed.
 *
 * The PM pipeline may return lowercase action labels ('new', 'exit', 'add',
 * 'trim', 'hold', 'increase', 'decrease').  We normalise them to the five
 * canonical display kinds before rendering.
 *
 * Sizer-removed rows (action = 'exit', current_pct = 0 — the row was never held)
 * are de-emphasised in the display label — they are still shown so the user sees
 * what was rejected, but they do NOT surface as meaningful book-building changes.
 */

type ActionKind = 'EXIT' | 'OPEN' | 'TRIM' | 'ADD' | 'HOLD';

const ORDER: Record<ActionKind, number> = { EXIT: 0, OPEN: 1, TRIM: 2, ADD: 3, HOLD: 4 };

// Badge hues ride the sanctioned EVENT_COLORS map (lib/chart-colors.ts) — the
// same four-way identity coding as the chart event markers and drilldown labels.
// Token-driven classes collapsed OPEN and ADD in dark mode (--up === --accent),
// so the non-HOLD kinds are fixed hues applied via inline style.
const STYLE: Record<ActionKind, { color: string | null; icon: typeof ArrowRight }> = {
  EXIT: { color: EVENT_COLORS.EXIT, icon: XCircle },
  OPEN: { color: EVENT_COLORS.OPEN, icon: PlusCircle },
  TRIM: { color: EVENT_COLORS.TRIM, icon: ArrowDownRight },
  ADD: { color: EVENT_COLORS.ADD, icon: ArrowUpRight },
  HOLD: { color: null, icon: ArrowRight },
};

/**
 * Normalise PM action strings to the canonical 5 display kinds.
 * PM may emit: 'new', 'open', 'add', 'increase', 'trim', 'decrease',
 *              'exit', 'hold' (all lowercase or mixed).
 */
function kindOf(action: string): ActionKind {
  const a = (action || '').trim().toUpperCase();
  if (a === 'NEW' || a === 'OPEN') return 'OPEN';
  if (a === 'ADD' || a === 'INCREASE') return 'ADD';
  if (a === 'TRIM' || a === 'DECREASE') return 'TRIM';
  if (a === 'EXIT') return 'EXIT';
  if (a === 'HOLD') return 'HOLD';
  // Unknown: treat as HOLD so it collapses rather than breaking the UI.
  return 'HOLD';
}

/**
 * True when the action is a sizer-rejected row (action = 'exit', current_pct = 0 —
 * the row was never held) — a pipeline artefact, not a real book-building decision.
 */
function isSizerRemoved(a: RebalanceAction): boolean {
  return kindOf(a.action) === 'EXIT' && (a.current_pct ?? 0) === 0;
}

function ActionRow({ a, rationale }: { a: RebalanceAction; rationale?: string }) {
  const kind = kindOf(a.action);
  const { color, icon: Icon } = STYLE[kind];
  const delta = (a.recommended_pct ?? 0) - (a.current_pct ?? 0);
  return (
    <div className="px-5 py-2.5 hover:bg-ink/[0.025] transition-colors">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span
            className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
              color ? '' : 'bg-ink/[0.06] text-ink-mute border-hair'
            }`}
            style={
              color
                ? { color, backgroundColor: withAlpha(color, 0.15), borderColor: withAlpha(color, 0.3) }
                : undefined
            }
          >
            <Icon size={11} />
            {kind}
          </span>
          <span className="font-mono text-xs font-bold text-ink">{a.ticker}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0 font-mono text-xs tabular-nums">
          <span className="text-ink-mute">{(a.current_pct ?? 0).toFixed(1)}%</span>
          <ArrowRight size={11} className="text-ink-mute/60" />
          <span className="text-ink font-semibold">{(a.recommended_pct ?? 0).toFixed(1)}%</span>
          {Math.abs(delta) >= 0.05 && (
            <span className={delta > 0 ? 'text-up' : 'text-down'}>
              {delta > 0 ? '+' : ''}
              {delta.toFixed(1)}pp
            </span>
          )}
        </div>
      </div>
      {rationale && (
        <p className="mt-1 pl-1 text-[11px] leading-snug text-ink-mute">{rationale}</p>
      )}
    </div>
  );
}

export function TodayActionsPanel({
  actions,
  rationaleByTicker,
  bare = false,
}: {
  actions: RebalanceAction[];
  /** Per-ticker rationale from the PM rebalance memo (#704); the rationale line
   *  is omitted entirely for tickers with no memo entry. */
  rationaleByTicker?: Record<string, string>;
  /** Hero/embedded mode: drop the panel's own glass-card frame and the
   *  "Today's actions" header (the host supplies the title and the frame). */
  bare?: boolean;
}) {
  const [showHolds, setShowHolds] = useState(false);
  const [showRemoved, setShowRemoved] = useState(false);
  const rationale = (ticker: string): string | undefined =>
    rationaleByTicker?.[ticker.trim().toUpperCase()];
  const { changes, holds, sizerRemoved } = useMemo(() => {
    const sorted = [...actions].sort((x, y) => ORDER[kindOf(x.action)] - ORDER[kindOf(y.action)]);
    return {
      // Meaningful book-building actions: new, add, trim, exit (where current_pct > 0).
      changes: sorted.filter((a) => kindOf(a.action) !== 'HOLD' && !isSizerRemoved(a)),
      holds: sorted.filter((a) => kindOf(a.action) === 'HOLD'),
      // Sizer-rejected rows (target=0, never held) — shown collapsed so they don't crowd
      // the meaningful actions but are still accessible for inspection.
      sizerRemoved: sorted.filter((a) => isSizerRemoved(a)),
    };
  }, [actions]);

  return (
    <div
      className={
        bare ? 'rounded-lg border border-hair/70 overflow-hidden' : 'glass-card p-0 overflow-hidden'
      }
    >
      {!bare && (
        <div className="px-5 py-3.5 border-b border-hair bg-term-bg flex items-center justify-between">
          <div className="flex items-center gap-2">
            {/* Decision chrome, not P&L (F5) — calm accent, matching the pipeline decision pips. */}
            <ListChecks size={15} className="text-accent" />
            <h3 className="text-sm font-semibold">Today&rsquo;s actions</h3>
            {changes.length > 0 && (
              <span className="rounded-full bg-accent/15 text-accent border border-accent/30 px-2 py-0.5 text-[10px] font-bold tabular-nums">
                {changes.length}
              </span>
            )}
          </div>
          <Link
            href="/why?why=deliberations"
            className="text-[10px] text-accent hover:underline font-medium"
          >
            Full rebalance memo →
          </Link>
        </div>
      )}

      {changes.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-ink-mute">
          {actions.length === 0
            ? 'No rebalance proposed for the latest run.'
            : 'No changes proposed — portfolio is at target weights.'}
        </p>
      ) : (
        <div className="divide-y divide-hair">
          {changes.map((a, i) => (
            <ActionRow key={`${a.ticker}-${i}`} a={a} rationale={rationale(a.ticker)} />
          ))}
        </div>
      )}

      {holds.length > 0 && (
        <div className="border-t border-hair">
          <button
            type="button"
            onClick={() => setShowHolds((v) => !v)}
            className="w-full px-5 py-2 text-left text-[11px] text-ink-mute hover:text-ink-soft transition-colors"
          >
            {showHolds ? '▾' : '▸'} {holds.length} position{holds.length !== 1 ? 's' : ''} held
          </button>
          {showHolds && (
            <div className="divide-y divide-hair/60">
              {holds.map((a, i) => (
                <ActionRow key={`hold-${a.ticker}-${i}`} a={a} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Sizer-removed rows: collapsed by default so they don't bury book-building actions */}
      {sizerRemoved.length > 0 && (
        <div className="border-t border-hair">
          <button
            type="button"
            onClick={() => setShowRemoved((v) => !v)}
            className="w-full px-5 py-2 text-left text-[11px] text-ink-mute hover:text-ink-soft transition-colors"
          >
            {showRemoved ? '▾' : '▸'} {sizerRemoved.length} removed by risk sizing
          </button>
          {showRemoved && (
            <div className="divide-y divide-hair/60">
              {sizerRemoved.map((a, i) => (
                <ActionRow key={`removed-${a.ticker}-${i}`} a={a} rationale={rationale(a.ticker)} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
