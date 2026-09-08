'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { Button } from '@digithings/web';
import type { DecisionLogRow } from '@/lib/holdings-decisions';
import { directionAdjustedAlpha } from '@/lib/decision-scorecard';
import { buildPipelineHref } from '@/lib/pipeline-links';
import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';
import { fmtPct, signColorClass } from '@/components/observability/shared';

const DEFAULT_VISIBLE_ROWS = 6;

function OutcomeCell({ status, value }: { status: string; value: number | null }) {
  if (status !== 'resolved') {
    return <span className="text-xs text-ink-mute">Awaiting</span>;
  }
  const pct = value != null ? value * 100 : null;
  return <span className={signColorClass(pct)}>{fmtPct(pct)}</span>;
}

export default function ConvictionHistory({ decisions }: { decisions: DecisionLogRow[] }) {
  const [showAll, setShowAll] = useState(false);
  const sorted = [...decisions].sort((a, b) =>
    (b.run_date ?? '').localeCompare(a.run_date ?? '')
  );

  if (!sorted.length) {
    return (
      <section className="decision-ledger border-y border-hair px-4 py-6 md:px-5">
        <h2 className="text-sm font-semibold text-ink">Analysis history</h2>
        <p className="mt-2 text-sm text-ink-mute">
          No Pipeline decisions are recorded for this ticker.
        </p>
      </section>
    );
  }

  const visibleRows = showAll ? sorted : sorted.slice(0, DEFAULT_VISIBLE_ROWS);
  const hiddenCount = sorted.length - DEFAULT_VISIBLE_ROWS;

  return (
    <section className="decision-ledger border-y border-hair" aria-labelledby="analysis-history-heading">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-hair px-4 py-4 md:px-5">
        <div className="space-y-1">
          <p className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
            Pipeline record
          </p>
          <h2 id="analysis-history-heading" className="text-sm font-semibold text-ink">
            Analysis history
          </h2>
        </div>
        <span className="font-mono text-[11px] text-ink-mute">
          {sorted.length} {sorted.length === 1 ? 'analysis' : 'analyses'}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm tabular-nums">
          <thead>
            <tr className="border-b border-hair text-left font-mono text-[11px] uppercase text-ink-mute">
              <th className="px-4 py-2.5 font-normal md:px-5">Date</th>
              <th className="py-2.5 pr-4 font-normal">View</th>
              <th className="py-2.5 pr-4 text-right font-normal">Conviction</th>
              <th className="py-2.5 pr-4 font-normal">Outcome</th>
              <th className="py-2.5 pr-4 text-right font-normal">Return</th>
              <th className="py-2.5 pr-4 text-right font-normal">Decision edge</th>
              <th className="py-2.5 pr-4 text-right font-normal">Source</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((decision) => {
              const edge = decision.alpha == null
                ? null
                : directionAdjustedAlpha(decision.alpha, decision.stance);
              const pipelineHref = buildPipelineHref({
                date: decision.run_date,
                stage: 'selection',
              });
              return (
                <tr key={decision.id} className="border-b border-hair/50">
                  <td className="px-4 py-3 font-mono text-xs text-ink-mute md:px-5">
                    {decision.run_date ?? '—'}
                  </td>
                  <td className="py-3 pr-4 font-medium capitalize text-ink">
                    {decision.stance ?? '—'}
                  </td>
                  <td className="py-3 pr-4 text-right">
                    {decision.conviction != null ? (
                      <SignedConvictionBadge value={decision.conviction} />
                    ) : (
                      <span className="text-ink-mute">—</span>
                    )}
                  </td>
                  <td className="py-3 pr-4 text-xs text-ink-soft">
                    {decision.status === 'resolved'
                      ? `Scored${decision.holding_days != null ? ` · ${decision.holding_days}d` : ''}`
                      : 'Awaiting outcome'}
                  </td>
                  <td className="py-3 pr-4 text-right">
                    <OutcomeCell status={decision.status} value={decision.actual_return} />
                  </td>
                  <td className={`py-3 pr-4 text-right ${signColorClass(edge)}`}>
                    {decision.status === 'resolved'
                      ? fmtPct(edge == null ? null : edge * 100)
                      : '—'}
                  </td>
                  <td className="py-3 pr-4 text-right">
                    <Link
                      href={pipelineHref}
                      className="inline-flex items-center gap-1 text-xs text-accent hover:underline"
                    >
                      Open in Pipeline <ArrowUpRight size={13} aria-hidden />
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {hiddenCount > 0 ? (
        <div className="flex justify-center border-t border-hair px-4 py-3">
          <Button
            dress="reference"
            variant="quiet"
            onClick={() => setShowAll(!showAll)}
            aria-label={showAll ? 'Show fewer analyses' : `Show ${hiddenCount} older analyses`}
          >
            {showAll ? 'Show fewer' : `Show ${hiddenCount} older`}
          </Button>
        </div>
      ) : null}
    </section>
  );
}