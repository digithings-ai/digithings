'use client';

import Link from 'next/link';
import type { Position } from '@/lib/types';
import type { ProposedDecision } from '@/lib/holdings-decisions';
import { buildPipelineHref } from '@/lib/pipeline-links';
import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';
import { AsOfBadge } from '@/components/shared/as-of-badge';

function dossierHref(ticker: string): string {
  return `/portfolio/tickers?ticker=${encodeURIComponent(ticker.toUpperCase())}`;
}

/**
 * Trailing "unassigned" shelf: the two honest buckets the story spine cannot
 * place. Copy states the backend gap plainly so the empty linkage never reads as
 * a rendering bug.
 */
export function UnassignedShelf({
  heldUnmapped,
  proposedUnheld,
}: {
  heldUnmapped: Position[];
  proposedUnheld: ProposedDecision[];
}) {
  if (heldUnmapped.length === 0 && proposedUnheld.length === 0) return null;

  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <h2 className="font-display text-2xl text-ink">Not tied to a market view</h2>
        <p className="max-w-3xl text-xs leading-relaxed text-ink-mute">
          Vehicle→market links in the pipeline are currently unreliable; this view derives the
          hierarchy from the analyst&rsquo;s vehicle-selection map (
          <span className="font-mono">thesis_vehicles</span>). Tickers below weren&rsquo;t mapped
          to a current market view on the shown date.
        </p>
      </div>

      {heldUnmapped.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-ink-soft">Held, not yet tied to a market view</h3>
          <div className="glass-card divide-y divide-hair overflow-hidden p-0">
            {heldUnmapped.map((p) => (
              <Link
                key={p.ticker}
                href={dossierHref(p.ticker)}
                className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-ink/[0.03] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
              >
                <span className="w-16 shrink-0 font-mono text-sm font-semibold text-ink">
                  {p.ticker}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm text-ink-soft" title={p.name}>
                  {p.name}
                </span>
                <span className="w-16 shrink-0 text-right font-mono text-sm tabular-nums text-ink">
                  {(p.weight_actual ?? 0).toFixed(1)}%
                </span>
              </Link>
            ))}
          </div>
        </div>
      ) : null}

      {proposedUnheld.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-ink-soft">Proposed, not held</h3>
          <div className="glass-card divide-y divide-hair overflow-hidden p-0">
            {proposedUnheld.map((d) => (
              <div key={d.ticker} className="flex items-center gap-3 px-4 py-3">
                <Link
                  href={dossierHref(d.ticker)}
                  className="w-16 shrink-0 font-mono text-sm font-semibold text-ink hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
                >
                  {d.ticker}
                </Link>
                {d.stance ? <span className="text-sm capitalize text-ink-soft">{d.stance}</span> : null}
                {d.conviction != null ? <SignedConvictionBadge value={d.conviction} /> : null}
                <span className="ml-auto flex items-center gap-3">
                  {d.runDate ? <AsOfBadge date={d.runDate} /> : null}
                  <Link
                    href={buildPipelineHref({ node: d.node, stage: 'selection' })}
                    className="text-xs text-accent hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
                  >
                    Deliberation
                  </Link>
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
