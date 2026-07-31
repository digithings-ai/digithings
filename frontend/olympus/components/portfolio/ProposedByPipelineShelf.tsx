'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ExternalLink } from 'lucide-react';
import { Button } from '@digithings/web';
import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';
import { buildPipelineHref } from '@/lib/pipeline-links';
import type { ProposedDecision } from '@/lib/holdings-decisions';

const DEFAULT_VISIBLE = 6;

/**
 * Decision-log tickers the book does NOT hold — the pipeline's standing suggestions.
 * Each row deep-links to its analyst node in Pipeline. Absent (null) when empty.
 * Flat divided section with hairlines (no glass-card).
 */
export default function ProposedByPipelineShelf({ proposed }: { proposed: ProposedDecision[] }) {
  const [showAll, setShowAll] = useState(false);

  if (!proposed.length) return null;

  const visible = showAll ? proposed : proposed.slice(0, DEFAULT_VISIBLE);
  const remaining = proposed.length - DEFAULT_VISIBLE;

  return (
    <section className="border border-hair bg-surface">
      <div className="border-b border-hair bg-term-bg px-4 py-3 md:px-6">
        <h3 className="text-sm font-semibold text-ink">Proposed by the pipeline</h3>
        <p className="mt-0.5 text-xs text-ink-mute">
          Decisions on tickers the book does not hold — open the analyst memo to see why.
        </p>
      </div>
      <ul className="divide-y divide-hair">
        {visible.map((d) => (
          <li key={d.ticker} className="flex items-center justify-between gap-3 px-4 py-3 md:px-6">
            <div className="flex items-center gap-3">
              <span className="font-mono font-semibold text-ink">{d.ticker}</span>
              {d.conviction != null && <SignedConvictionBadge value={d.conviction} />}
              {d.stance && <span className="text-xs capitalize text-ink-mute">{d.stance}</span>}
            </div>
            <Link
              href={buildPipelineHref({ date: d.runDate, stage: 'selection', node: d.node })}
              className="inline-flex items-center gap-1 text-xs text-accent hover:underline"
            >
              Open in Pipeline
              <ExternalLink size={12} aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
      {remaining > 0 && (
        <div className="border-t border-hair px-4 py-3 text-center md:px-6">
          <Button
            variant="quiet"
            onClick={() => setShowAll(!showAll)}
            className="text-xs"
          >
            {showAll ? 'Show fewer' : `Show ${remaining} more`}
          </Button>
        </div>
      )}
    </section>
  );
}
