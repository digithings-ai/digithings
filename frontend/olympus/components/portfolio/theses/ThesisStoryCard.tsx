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

function formatTimeframe(horizon: string): string {
  const value = horizon.replaceAll('_', ' ').replaceAll('-', ' ').trim();
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : horizon;
}

function dossierHref(ticker: string): string {
  return `/portfolio/tickers?ticker=${encodeURIComponent(ticker.toUpperCase())}`;
}

function deliberationHref(ticker: string): string {
  return buildPipelineHref({ node: decisionNodeFor(ticker), stage: 'selection' });
}

/**
 * One market thesis as a flat numbered disclosure row: header (rank · name ·
 * confidence · horizon · status), the thesis statement,
 * the confirm/break criteria, and the vehicles expressing the view. Closed by
 * default — callers control which thesis opens via the `defaultOpen` prop to
 * keep the disclosure spine scannable (#1607).
 */
export function ThesisStoryCard({
  story,
  defaultOpen = false,
  rank,
}: {
  story: ThesisStory;
  defaultOpen?: boolean;
  rank?: number;
}) {
  const { thesis, vehicles, asOf } = story;
  const pips = confidenceToPips(thesis.confidence);
  const confidenceLabel =
    thesis.confidence != null
      ? `${Math.round(thesis.confidence * 100)}% confidence`
      : 'Confidence not set';

  return (
    <details
      className="group border-y border-hair first:border-t-0 last:border-b-0"
      open={defaultOpen}
    >
      <summary className="cursor-pointer list-none px-4 py-4 transition-colors hover:bg-ink/[0.02] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50 [&::-webkit-details-marker]:hidden">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            {rank != null && (
              <span className="font-mono text-sm text-ink-mute">
                {String(rank).padStart(2, '0')}
              </span>
            )}
            <ChevronRight
              size={18}
              aria-hidden
              className="mt-0.5 shrink-0 text-ink-mute transition-transform group-open:rotate-90"
            />
            <h3 className="font-display text-xl leading-snug text-ink">{thesis.name}</h3>
          </div>
          {isNonActive(thesis.status) ? (
            <span className="shrink-0 rounded-full border border-warn/40 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-warn">
              {thesis.status}
            </span>
          ) : null}
        </div>

      </summary>

      <div className="space-y-5 px-4 pb-5 pl-[3.25rem]">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-hair pb-3">
          <div className="flex items-center gap-2">
            <ConvictionMeter value={pips} max={CONFIDENCE_PIPS} srLabel={confidenceLabel} />
            <span className="text-xs tabular-nums text-ink-mute">{confidenceLabel}</span>
          </div>
          {thesis.horizon ? (
            <span className="text-xs text-ink-soft">
              {formatTimeframe(thesis.horizon)}
            </span>
          ) : null}
        </div>
        {thesis.notes ? (
          <p className="whitespace-pre-line text-sm leading-relaxed text-ink-soft">
            {thesis.notes}
          </p>
        ) : null}

        <ThesisCriteriaColumns
          validation={thesis.validation_criteria}
          invalidation={thesis.invalidation_criteria}
        />

        <section className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <h4 className="text-xs uppercase tracking-wider text-ink-mute">
              Vehicles expressing this view
            </h4>
            {asOf ? <AsOfBadge date={asOf} /> : null}
          </div>
          {vehicles.length === 0 ? (
            <p className="text-sm text-ink-mute">
              No vehicle was mapped to this view on the shown date.
            </p>
          ) : (
            <div className="overflow-hidden border-y border-hair">
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
