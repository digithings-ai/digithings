'use client';

import Link from 'next/link';
import { ChevronRight, ArrowUpRight } from 'lucide-react';
import type { ThesisStory } from '@/lib/thesis-story';
import { decisionNodeFor } from '@/lib/holdings-decisions';
import { buildPipelineHref } from '@/lib/pipeline-links';
import { ConvictionMeter } from '@/components/shared/conviction-meter';
import { AsOfBadge } from '@/components/shared/as-of-badge';
import { ThesisCriteriaColumns } from '@/components/portfolio/theses/ThesisCriteriaColumns';
import { VehicleExpressionRow } from '@/components/portfolio/theses/VehicleExpressionRow';

const CONFIDENCE_PIPS = 4;

function confidenceToPips(confidence: number | null): number {
  if (confidence == null) return 0;
  return Math.max(0, Math.min(CONFIDENCE_PIPS, Math.round(confidence * CONFIDENCE_PIPS)));
}

function isNonActive(status: string | null): boolean {
  const s = (status ?? '').toLowerCase();
  return Boolean(s) && !s.includes('active');
}

function dossierHref(ticker: string): string {
  return `/portfolio/tickers?ticker=${encodeURIComponent(ticker.toUpperCase())}`;
}

function deliberationHref(ticker: string): string {
  return buildPipelineHref({ node: decisionNodeFor(ticker), stage: 'selection' });
}

/**
 * One market thesis as the spine of the story: header (name · confidence meter ·
 * horizon · status · drives X% of book), the thesis statement, the confirm/break
 * criteria, and the vehicles expressing the view. Defaults open — the tab reads
 * as a narrative, not a dense index.
 */
export function ThesisStoryCard({
  story,
  bookWeightPct,
}: {
  story: ThesisStory;
  bookWeightPct: number;
}) {
  const { thesis, vehicles, asOf } = story;
  const pips = confidenceToPips(thesis.confidence);
  const confidenceLabel =
    thesis.confidence != null
      ? `${Math.round(thesis.confidence * 100)}% confidence`
      : 'Confidence not set';

  return (
    <details className="group glass-card overflow-hidden p-0" open>
      <summary className="flex cursor-pointer list-none flex-col gap-3 p-5 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50 [&::-webkit-details-marker]:hidden">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-2">
            <ChevronRight
              size={18}
              aria-hidden
              className="mt-1 shrink-0 text-ink-mute transition-transform group-open:rotate-90"
            />
            <h3 className="font-display text-xl leading-snug text-ink">{thesis.name}</h3>
          </div>
          {isNonActive(thesis.status) ? (
            <span className="shrink-0 rounded-full border border-warn/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-warn">
              {thesis.status}
            </span>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 pl-7">
          <div className="flex items-center gap-2">
            <ConvictionMeter value={pips} max={CONFIDENCE_PIPS} srLabel={confidenceLabel} />
            <span className="text-xs tabular-nums text-ink-mute">{confidenceLabel}</span>
          </div>
          {thesis.horizon ? (
            <span className="rounded-md border border-hair px-2 py-0.5 text-[11px] text-ink-soft">
              {thesis.horizon}
            </span>
          ) : null}
          <span className="ml-auto text-sm text-ink-soft">
            <span className="text-ink-mute">drives </span>
            <span className="font-mono font-semibold tabular-nums text-ink">
              {bookWeightPct.toFixed(1)}%
            </span>
            <span className="text-ink-mute"> of the book</span>
          </span>
        </div>
      </summary>

      <div className="space-y-5 px-5 pb-5">
        {thesis.notes ? (
          <p className="whitespace-pre-line pl-7 text-sm leading-relaxed text-ink-soft">
            {thesis.notes}
          </p>
        ) : null}

        <ThesisCriteriaColumns
          validation={thesis.validation_criteria}
          invalidation={thesis.invalidation_criteria}
        />

        <section className="space-y-2">
          <div className="flex items-center justify-between gap-3 pl-1">
            <h4 className="font-mono text-[10px] uppercase tracking-wider text-ink-mute">
              Vehicles expressing this view
            </h4>
            {asOf ? <AsOfBadge date={asOf} /> : null}
          </div>
          {vehicles.length === 0 ? (
            <p className="text-sm text-ink-mute">
              No vehicle was mapped to this view on the shown date.
            </p>
          ) : (
            <div className="glass-card overflow-hidden p-0">
              {vehicles.map((v) => (
                <VehicleExpressionRow
                  key={v.ticker}
                  ticker={v.ticker}
                  rationale={v.rationale}
                  candidateRank={v.candidateRank}
                  position={v.position}
                  latestDecision={v.latestDecision}
                  dossierHref={dossierHref(v.ticker)}
                  deliberationHref={deliberationHref(v.ticker)}
                />
              ))}
            </div>
          )}
        </section>

        <Link
          href={`/portfolio/theses/${encodeURIComponent(thesis.id)}`}
          className="inline-flex items-center gap-1 text-xs text-accent hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
        >
          Open thesis detail <ArrowUpRight size={12} aria-hidden />
        </Link>
      </div>
    </details>
  );
}
