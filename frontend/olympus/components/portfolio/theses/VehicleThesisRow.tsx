'use client';

import Link from 'next/link';
import type { Thesis } from '@/lib/types';
import { ConvictionMeter } from '@/components/shared/conviction-meter';

const CONFIDENCE_PIPS = 4;

function confidenceToPips(confidence: number | null): number {
  if (confidence == null) return 0;
  return Math.max(0, Math.min(CONFIDENCE_PIPS, Math.round(confidence * CONFIDENCE_PIPS)));
}

export function VehicleThesisRow({
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
      className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-white/[0.03] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
    >
      {thesis.vehicle ? (
        <span className="w-16 shrink-0 font-mono text-sm font-semibold text-text-primary">
          {thesis.vehicle}
        </span>
      ) : null}
      <span className="min-w-0 flex-1 truncate text-sm text-text-secondary" title={thesis.name}>
        {thesis.name}
      </span>
      <ConvictionMeter value={pips} max={CONFIDENCE_PIPS} srLabel={confidenceLabel} />
      <span className="w-16 shrink-0 text-right font-mono text-sm tabular-nums text-text-primary">
        {bookWeightPct.toFixed(1)}%
      </span>
    </Link>
  );
}
