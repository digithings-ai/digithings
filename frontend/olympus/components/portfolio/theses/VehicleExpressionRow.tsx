'use client';

import Link from 'next/link';
import { ChevronRight, ArrowUpRight } from 'lucide-react';
import type { Position } from '@/lib/types';
import type { DecisionLogRow } from '@/lib/holdings-decisions';
import { ConvictionMeter } from '@/components/shared/conviction-meter';
import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';
import { AsOfBadge } from '@/components/shared/as-of-badge';
import { Badge } from '@/components/ui';

/** "12.3%" style, signed for P&L. Tone applied by the caller (P&L-only --up/--down). */
function fmtPct(v: number | null | undefined, signed = false): string {
  if (v == null || Number.isNaN(v)) return '—';
  const s = signed && v > 0 ? '+' : '';
  return `${s}${v.toFixed(1)}%`;
}

function pnlTone(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return 'text-ink';
  return v >= 0 ? 'text-up' : 'text-down';
}

/** A labelled entry/exit envelope chip; renders "—" when the advisory field is unset. */
function EnvelopeChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs uppercase tracking-wider text-ink-mute">{label}</span>
      <span className="font-mono text-sm tabular-nums text-ink">{value}</span>
    </div>
  );
}

/**
 * Level-2/3 row of the thesis story spine: a vehicle expressing a market view.
 * The summary carries the selection (ticker · rationale · #rank · held metrics);
 * expanding reveals the stock-level TIMING story (entry/exit envelope, the latest
 * signed analyst call, and the dossier / deliberation deep links).
 */
export function VehicleExpressionRow({
  ticker,
  rationale,
  candidateRank,
  position,
  latestDecision,
  dossierHref,
  deliberationHref,
}: {
  ticker: string;
  rationale: string | null;
  candidateRank: number | null;
  position: Position | null;
  latestDecision: DecisionLogRow | null;
  dossierHref: string;
  deliberationHref: string;
}) {
  const held = position != null;
  const sinceEntry = position?.since_entry_return_pct ?? position?.unrealized_pnl_pct ?? null;
  const hasEnvelope =
    position != null &&
    (position.stop_loss_pct != null ||
      position.target_pct_gain != null ||
      position.horizon_days != null);
  const conviction = latestDecision?.conviction ?? null;
  const pending = latestDecision?.status === 'pending';

  return (
    <details className="group border-t border-hair first:border-t-0">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 transition-colors hover:bg-ink/[0.03] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50 [&::-webkit-details-marker]:hidden">
        <ChevronRight
          size={14}
          aria-hidden
          className="shrink-0 text-ink-mute transition-transform group-open:rotate-90"
        />
        <span className="w-14 shrink-0 font-mono text-sm font-semibold text-ink">{ticker}</span>
        {candidateRank != null ? (
          <Badge variant={candidateRank === 1 ? 'blue' : 'default'}>
            {candidateRank === 1 ? '#1 pick' : `#${candidateRank}`}
          </Badge>
        ) : null}
        <span className="min-w-0 flex-1 truncate text-sm text-ink-soft" title={rationale ?? undefined}>
          {rationale ?? 'No selection rationale recorded.'}
        </span>
        {held ? (
          <span className="hidden shrink-0 items-center gap-3 sm:flex">
            <span className={`font-mono text-sm tabular-nums ${pnlTone(sinceEntry)}`}>
              {fmtPct(sinceEntry, true)}
            </span>
            <span className="w-14 text-right font-mono text-sm tabular-nums text-ink">
              {fmtPct(position?.weight_actual)}
            </span>
          </span>
        ) : (
          <span className="shrink-0 text-xs uppercase tracking-wider text-ink-mute">
            not held
          </span>
        )}
      </summary>

      <div className="space-y-4 px-4 pb-4 pl-11">
        {/* Held metrics + entry/exit envelope (TIMING) */}
        {held ? (
          <div className="flex flex-wrap gap-x-8 gap-y-3">
            <EnvelopeChip label="Weight" value={fmtPct(position?.weight_actual)} />
            <EnvelopeChip
              label="Since entry"
              value={fmtPct(sinceEntry, true)}
            />
            {position?.entry_price != null ? (
              <EnvelopeChip
                label="Entry"
                value={`$${position.entry_price.toFixed(2)}${position.entry_date ? ` · ${position.entry_date}` : ''}`}
              />
            ) : null}
            {hasEnvelope ? (
              <>
                <EnvelopeChip
                  label="Stop"
                  value={position?.stop_loss_pct != null ? fmtPct(position.stop_loss_pct) : '—'}
                />
                <EnvelopeChip
                  label="Target"
                  value={position?.target_pct_gain != null ? fmtPct(position.target_pct_gain, true) : '—'}
                />
                <EnvelopeChip
                  label="Horizon"
                  value={position?.horizon_days != null ? `${position.horizon_days}d` : '—'}
                />
              </>
            ) : null}
          </div>
        ) : (
          <p className="text-xs text-ink-mute">
            Proposed vehicle — the book does not currently hold this ticker.
          </p>
        )}

        {/* Latest signed analyst call */}
        {latestDecision ? (
          <div className="flex flex-wrap items-center gap-3 text-sm text-ink-soft">
            <span className="text-xs uppercase tracking-wider text-ink-mute">
              Latest call
            </span>
            {latestDecision.stance ? (
              <span className="capitalize text-ink">{latestDecision.stance}</span>
            ) : null}
            {conviction != null ? <SignedConvictionBadge value={conviction} /> : null}
            {pending ? (
              <span className="text-xs text-ink-mute">open — not yet resolved</span>
            ) : null}
            <AsOfBadge date={latestDecision.run_date ?? null} />
          </div>
        ) : null}

        {/* Deep links */}
        <div className="flex flex-wrap gap-4 text-xs">
          <Link
            href={dossierHref}
            className="inline-flex items-center gap-1 text-accent hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
          >
            Open ticker dossier <ArrowUpRight size={12} aria-hidden />
          </Link>
          <Link
            href={deliberationHref}
            className="inline-flex items-center gap-1 text-ink-soft hover:text-ink hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
          >
            Open deliberation <ArrowUpRight size={12} aria-hidden />
          </Link>
        </div>
      </div>
    </details>
  );
}
