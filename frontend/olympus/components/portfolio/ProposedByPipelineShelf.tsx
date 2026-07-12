'use client';

import { ExternalLink } from 'lucide-react';
import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';
import { buildPipelineHref } from '@/lib/pipeline-links';
import type { ProposedDecision } from '@/lib/holdings-decisions';

/**
 * Decision-log tickers the book does NOT hold — the pipeline's standing suggestions.
 * Each row deep-links to its analyst node in Pipeline. Absent (null) when empty.
 */
export default function ProposedByPipelineShelf({ proposed }: { proposed: ProposedDecision[] }) {
  if (!proposed.length) return null;
  return (
    <section className="glass-card p-0 overflow-hidden">
      <div className="border-b border-hair bg-term-bg px-4 py-3 md:px-6">
        <h3 className="text-sm font-semibold text-ink">Proposed by the pipeline</h3>
        <p className="mt-0.5 text-xs text-ink-mute">
          Decisions on tickers the book does not hold — open the analyst memo to see why.
        </p>
      </div>
      <ul className="divide-y divide-hair">
        {proposed.map((d) => (
          <li key={d.ticker} className="flex items-center justify-between gap-3 px-4 py-3 md:px-6">
            <div className="flex items-center gap-3">
              <span className="font-mono font-semibold text-ink">{d.ticker}</span>
              {d.conviction != null && <SignedConvictionBadge value={d.conviction} />}
              {d.stance && <span className="text-xs capitalize text-ink-mute">{d.stance}</span>}
            </div>
            <a
              href={buildPipelineHref({ date: d.runDate, stage: 'selection', node: d.node })}
              className="inline-flex items-center gap-1 text-xs text-[var(--accent)] hover:underline"
            >
              Open in Pipeline
              <ExternalLink size={12} aria-hidden />
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
