'use client';

import type { Mover } from '@/lib/twelve-x/types';
import DeltaChip from './DeltaChip';

/**
 * A horizontally-scrollable strip of the biggest consensus shifts since the last run.
 *
 * F5 ruling (#1450): the mover chips stay LOCAL glass-card `<button>`s — the
 * promoted controls Card is a non-interactive `<div>` in a different dress
 * (ctl-card-ref: 12px radius, no shadow/hover), and `.glass-card` is
 * load-bearing for MotionLayer's scroll-reveal system (globals.css
 * `html.motion-on .glass-card`). Same ruling as F4's StatCard; it covers the
 * glass-card panel cards across the twelve-x tabs for the same two reasons.
 */
export interface MoversStripProps {
  movers: Mover[];
  onSelect?: (currency: string) => void;
  title?: string;
  className?: string;
}

export default function MoversStrip({
  movers,
  onSelect,
  title = 'Biggest shifts since last run',
  className,
}: MoversStripProps) {
  if (movers.length === 0) return null;

  return (
    <div className={className}>
      <div className="text-[10px] font-medium uppercase tracking-wide text-ink-mute mb-1.5">
        {title}
      </div>
      <div className="flex gap-2 overflow-x-auto -mx-1 px-1 snap-x">
        {movers.map((m) => (
          <button
            key={m.currency}
            type="button"
            onClick={() => onSelect?.(m.currency)}
            className="snap-start shrink-0 glass-card px-2.5 py-1.5 flex items-center gap-1.5 hover:bg-ink/[0.04] transition-colors"
          >
            <span className="font-mono font-semibold text-ink">{m.currency}</span>
            <span className="tabular-nums text-[11px] font-mono text-ink-soft">
              {m.scoreNow.toFixed(2)}
            </span>
            <DeltaChip delta={m.scoreDelta} />
          </button>
        ))}
      </div>
    </div>
  );
}
