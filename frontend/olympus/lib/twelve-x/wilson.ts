/**
 * Wilson score interval for a binomial proportion (95% by default).
 * Matches twelve-x `eval_metrics.wilson_interval`.
 */

const WILSON_Z = 1.959963984540054;

export interface WilsonInterval {
  low: number;
  high: number;
  n: number;
  k: number;
  rate: number;
}

export function wilsonInterval(k: number, n: number, z = WILSON_Z): WilsonInterval {
  if (n <= 0) return { low: 0, high: 1, n: 0, k: 0, rate: 0 };
  if (k < 0 || k > n) throw new Error(`k must be in [0, n]; got k=${k}, n=${n}`);
  const phat = k / n;
  const z2 = z * z;
  const denom = 1 + z2 / n;
  const centre = phat + z2 / (2 * n);
  const margin = z * Math.sqrt((phat * (1 - phat) + z2 / (4 * n)) / n);
  return {
    low: Math.max(0, (centre - margin) / denom),
    high: Math.min(1, (centre + margin) / denom),
    n,
    k,
    rate: phat,
  };
}

export function formatWilsonPct(iv: WilsonInterval): string {
  if (iv.n === 0) return 'n=0';
  const pct = (x: number) => `${(100 * x).toFixed(0)}%`;
  return `${pct(iv.rate)} (n=${iv.n}, ${pct(iv.low)}–${pct(iv.high)})`;
}
