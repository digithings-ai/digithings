'use client';

import { useState } from 'react';
import { Button } from '@digithings/web';
import type { DecisionLogRow } from '@/lib/holdings-decisions';
import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';
import { fmtPct, signColorClass } from '@/components/observability/shared';

const DEFAULT_VISIBLE_ROWS = 6;

/**
 * Signed-conviction timeline + resolved-calls table over `decision_log`, scoped
 * to one ticker (#1562 PR2). Reuses the decision-scorecard grammar
 * (`components/observability/DecisionScorecardTab.tsx`: same columns, same
 * `fmtPct`/`signColorClass` helpers) rather than re-deriving it.
 *
 * `status='pending'` rows carry `actual_return: null, alpha: null` — these
 * render as "open", never as a 0%/blank resolved call (#1562 §2 staleness
 * rule), so an in-flight call never reads as a wash.
 *
 * History is bounded to 6 recent rows by default with a "Show N older" / "Show fewer"
 * toggle to reveal the full timeline (#1607).
 */

function ReasoningExpander({ thesis, reflection }: { thesis: string | null; reflection: string | null }) {
  const [open, setOpen] = useState(false);
  if (!thesis && !reflection) {
    return <span className="text-xs italic text-ink-mute/50">none recorded</span>;
  }
  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-left text-xs text-ink-soft underline decoration-dotted underline-offset-2 hover:text-ink"
        aria-expanded={open}
      >
        {open ? 'hide' : 'show reasoning'}
      </button>
      {open && (
        <div className="mt-1 flex max-w-prose flex-col gap-2 text-xs">
          {thesis && (
            <div>
              <span className="font-medium text-ink-mute">Thesis: </span>
              <span className="text-ink-soft">{thesis}</span>
            </div>
          )}
          {reflection && (
            <div>
              <span className="font-medium text-ink-mute">Reflection: </span>
              <span className="text-ink-soft">{reflection}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Return/alpha cell — pending calls read "open", resolved calls read their signed pct. */
function OutcomeCell({ status, value }: { status: string; value: number | null }) {
  if (status !== 'resolved') {
    return <span className="text-xs italic text-ink-mute">open</span>;
  }
  const pct = value != null ? value * 100 : null;
  return <span className={signColorClass(pct)}>{fmtPct(pct)}</span>;
}

export default function ConvictionHistory({ decisions }: { decisions: DecisionLogRow[] }) {
  const [showAll, setShowAll] = useState(false);
  const sorted = [...decisions].sort((a, b) => (b.run_date ?? '').localeCompare(a.run_date ?? ''));

  if (sorted.length === 0) {
    return (
      <div className="glass-card space-y-2 p-5 md:p-6">
        <h2 className="font-display text-lg text-ink">Conviction history</h2>
        <p className="text-sm text-ink-mute">No analyst decisions on record for this ticker yet.</p>
      </div>
    );
  }

  const oldestFirst = [...sorted].reverse();
  const visibleRows = showAll ? sorted : sorted.slice(0, DEFAULT_VISIBLE_ROWS);
  const hiddenCount = sorted.length - DEFAULT_VISIBLE_ROWS;

  return (
    <div className="glass-card space-y-6 p-5 md:p-6">
      <h2 className="font-display text-lg text-ink">Conviction history</h2>

      {/* Timeline — oldest to newest, left to right. */}
      <div className="flex flex-wrap items-end gap-4 overflow-x-auto pb-1">
        {oldestFirst.map((d) => (
          <div key={d.id} className="flex shrink-0 flex-col items-center gap-1">
            {d.conviction != null ? (
              <SignedConvictionBadge value={d.conviction} />
            ) : (
              <span className="text-xs text-ink-mute">—</span>
            )}
            <span className="text-xs uppercase tracking-wider text-ink-mute">
              {d.run_date ?? '—'}
            </span>
            {d.status === 'pending' ? (
              <span className="text-xs italic text-ink-mute">open</span>
            ) : null}
          </div>
        ))}
      </div>

      {/* Resolved-calls table (includes pending rows, rendered as "open"). */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm tabular-nums">
          <thead>
            <tr className="border-b border-hair text-left text-xs text-ink-mute">
              <th className="py-2 pr-4 font-medium">Date</th>
              <th className="py-2 pr-4 font-medium">Stance</th>
              <th className="py-2 pr-4 text-right font-medium">Conviction</th>
              <th className="py-2 pr-4 text-right font-medium">Return</th>
              <th className="py-2 pr-4 text-right font-medium">Alpha</th>
              <th className="py-2 pr-4 text-right font-medium">Holding</th>
              <th className="py-2 font-medium">Reasoning</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((d) => (
              <tr key={d.id} className="border-b border-hair/50 align-top">
                <td className="py-2 pr-4 text-xs text-ink-mute">{d.run_date ?? '—'}</td>
                <td className="py-2 pr-4 capitalize text-ink-soft">{d.stance ?? '—'}</td>
                <td className="py-2 pr-4 text-right">
                  {d.conviction != null ? <SignedConvictionBadge value={d.conviction} /> : '—'}
                </td>
                <td className="py-2 pr-4 text-right">
                  <OutcomeCell status={d.status} value={d.actual_return} />
                </td>
                <td className="py-2 pr-4 text-right">
                  <OutcomeCell status={d.status} value={d.alpha} />
                </td>
                <td className="py-2 pr-4 text-right text-ink-soft">
                  {d.holding_days != null ? `${d.holding_days}d` : '—'}
                </td>
                <td className="py-2">
                  <ReasoningExpander thesis={d.thesis} reflection={d.reflection} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {hiddenCount > 0 && (
        <div className="flex justify-center">
          <Button
            dress="reference"
            variant="quiet"
            onClick={() => setShowAll(!showAll)}
            aria-label={showAll ? 'Show fewer decisions' : `Show ${hiddenCount} older decisions`}
          >
            {showAll ? 'Show fewer' : `Show ${hiddenCount} older`}
          </Button>
        </div>
      )}
    </div>
  );
}
