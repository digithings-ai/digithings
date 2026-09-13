'use client';

import { X } from 'lucide-react';
import { Sheet, SheetClose, SheetContent, SheetTitle } from '@digithings/web';
import type { FxConsensusDivergence } from '@/lib/twelve-x/types';
import { DEFAULT_DIVERGENCE_THRESHOLD } from '@/lib/twelve-x/divergence';

function fmtSigned(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
}

/**
 * Drill panel for a divergent currency — both reads, both as_of timestamps, raw snapshot.
 * Exported body for SSR tests (Sheet portal does not render under static markup).
 */
export function DivergencePanelBody({ divergence }: { divergence: FxConsensusDivergence }) {
  const rawJson =
    divergence.rawSnapshot != null
      ? JSON.stringify(divergence.rawSnapshot, null, 2)
      : null;

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h3 className="font-display text-2xl tracking-tight text-ink">{divergence.currency}</h3>
        <p className="text-sm text-ink-soft">
          Street vs PMT Smart Bias — gap {divergence.gap.toFixed(2)} (threshold{' '}
          {DEFAULT_DIVERGENCE_THRESHOLD})
        </p>
      </div>

      <section className="space-y-2 rounded-none border border-hair bg-term-bg p-4">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
          Twelve-x consensus
        </h4>
        <p className="text-sm text-ink">{divergence.streetStatement}</p>
        <p className="font-mono text-[11px] text-ink-mute">
          as_of {divergence.consensusAsOf}
        </p>
        <p className="font-mono text-[13px] text-ink-soft">
          Score {fmtSigned(divergence.consensusScore)} · tilt {fmtSigned(divergence.consensusTilt)}
        </p>
      </section>

      <section className="space-y-2 rounded-none border border-hair bg-term-bg p-4">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
          PMT Smart Bias
        </h4>
        <p className="text-sm text-ink">{divergence.pmtStatement}</p>
        <p className="font-mono text-[11px] text-ink-mute">week of {divergence.pmtAsOf}</p>
        <p className="font-mono text-[13px] text-ink-soft">
          Mapped score {fmtSigned(divergence.pmtScore)}
        </p>
      </section>

      {rawJson ? (
        <section className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
            Raw snapshot
          </h4>
          <pre className="max-h-64 overflow-auto rounded-none border border-hair bg-surface p-3 text-[10px] leading-relaxed text-ink-soft">
            {rawJson}
          </pre>
        </section>
      ) : null}
    </div>
  );
}

export default function DivergencePanel({
  divergence,
  open,
  onClose,
}: {
  divergence: FxConsensusDivergence | null;
  open: boolean;
  onClose: () => void;
}) {
  if (!divergence) return null;

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent side="right" className="w-full max-w-lg overflow-y-auto">
        <div className="flex items-start justify-between gap-3 pb-4">
          <SheetTitle className="sr-only">{divergence.currency} divergence</SheetTitle>
          <SheetClose
            type="button"
            className="ml-auto rounded-none p-1 text-ink-mute hover:text-ink"
            aria-label="Close divergence panel"
          >
            <X size={18} />
          </SheetClose>
        </div>
        <DivergencePanelBody divergence={divergence} />
      </SheetContent>
    </Sheet>
  );
}
