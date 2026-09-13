'use client';

import type { WilsonInterval } from '@/lib/twelve-x/wilson';

function pct(x: number): string {
  return `${(100 * x).toFixed(0)}%`;
}

/**
 * One calibrated hit-rate readout: point estimate plus the 95% Wilson score
 * interval, always with the raw k/n so small samples read honestly. `n = 0`
 * renders an em dash; `0 < n < insufficientN` carries a small-n flag.
 */
export function WilsonStat({
  label,
  interval,
  insufficientN = 10,
}: {
  label: string;
  interval: WilsonInterval;
  insufficientN?: number;
}) {
  const { k, n, rate, low, high } = interval;
  return (
    <div data-testid="wilson-stat">
      <p className="text-[10px] font-medium uppercase tracking-wider text-ink-mute">{label}</p>
      {n === 0 ? (
        <p className="font-mono text-sm tabular-nums text-ink">—</p>
      ) : (
        <p className="font-mono text-sm tabular-nums text-ink">
          {pct(rate)}
          <span className="ml-1.5 text-[11px] text-ink-mute">
            {k}/{n} · 95% CI {pct(low)}–{pct(high)}
            {n < insufficientN ? ' · small n' : ''}
          </span>
        </p>
      )}
    </div>
  );
}

export default WilsonStat;
