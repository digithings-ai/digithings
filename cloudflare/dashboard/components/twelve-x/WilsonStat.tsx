'use client';

import type { WilsonInterval } from '@/lib/twelve-x/wilson';

function pct(x: number): string {
  return `${(100 * x).toFixed(0)}%`;
}

/** Small-sample flag threshold; below this the readout carries a `small n` note. */
const INSUFFICIENT_N = 10;

/**
 * One calibrated hit-rate readout: point estimate plus the 95% Wilson score
 * interval, always with the raw k/n so small samples read honestly. `n = 0`
 * renders an em dash; `0 < n < 10` carries a small-n flag.
 */
export function WilsonStat({
  label,
  interval,
}: {
  label: string;
  interval: WilsonInterval;
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
            {n < INSUFFICIENT_N ? ' · small n' : ''}
          </span>
        </p>
      )}
    </div>
  );
}

export default WilsonStat;
