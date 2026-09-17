'use client';

import { Badge } from '@digithings/web/ui';

export interface DivergenceChipProps {
  gap: number;
  onClick?: () => void;
  className?: string;
}

/** Compact chip when street consensus and PMT Smart Bias disagree beyond threshold.
 *
 * Wave-2 (#4206): the hand-dressed button now rides the kit `Badge`
 * (variant="outline", `render` keeps the real `<button>` so the click/stop
 * propagation semantics and `data-divergence-chip` hook are unchanged) with
 * the warn token utilities for its tone. */
export default function DivergenceChip({ gap, onClick, className }: DivergenceChipProps) {
  const label = `Δ${gap.toFixed(2)}`;
  return (
    <Badge
      variant="outline"
      className={`border-warn/40 bg-warn/10 px-1.5 py-0.5 font-mono text-[10px] text-warn transition-colors hover:border-warn/60 hover:bg-warn/15${
        className ? ` ${className}` : ''
      }`}
      render={
        <button
          type="button"
          data-divergence-chip="true"
          onClick={(e) => {
            e.stopPropagation();
            onClick?.();
          }}
          title="Street consensus and PMT Smart Bias disagree — click for both reads"
        />
      }
    >
      {label}
    </Badge>
  );
}
