'use client';

import Link from 'next/link';
import type { Thesis } from '@/lib/types';
import { ConvictionMeter } from '@/components/shared/conviction-meter';

const CONFIDENCE_PIPS = 4;

function confidenceToPips(confidence: number | null): number {
  if (confidence == null) return 0;
  return Math.max(0, Math.min(CONFIDENCE_PIPS, Math.round(confidence * CONFIDENCE_PIPS)));
}

function isNonActive(status: string | null): boolean {
  const s = (status ?? '').toLowerCase();
  return Boolean(s) && !s.includes('active');
}

export function MarketViewCard({
  thesis,
  bookWeightPct,
  href,
}: {
  thesis: Thesis;
  bookWeightPct: number;
  href: string;
}) {
  const pips = confidenceToPips(thesis.confidence);
  const confidenceLabel =
    thesis.confidence != null ? `${Math.round(thesis.confidence * 100)}% confidence` : 'Confidence not set';

  return (
    <Link
      href={href}
      className="group glass-card block p-5 transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
    >
      <div className="flex items-start justify-between gap-4">
        <h3 className="font-display text-xl leading-snug text-ink group-hover:text-white">
          {thesis.name}
        </h3>
        {isNonActive(thesis.status) ? (
          <span className="shrink-0 rounded-full border border-warn/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-warn">
            {thesis.status}
          </span>
        ) : null}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2">
        <div className="flex items-center gap-2">
          <ConvictionMeter value={pips} max={CONFIDENCE_PIPS} srLabel={confidenceLabel} />
          <span className="text-xs text-ink-mute tabular-nums">{confidenceLabel}</span>
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
    </Link>
  );
}
