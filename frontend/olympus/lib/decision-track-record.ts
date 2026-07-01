/**
 * Decision track-record metrics — TS port of digiquant/.../atlas/backtest.py
 * (backtest_decisions). Pure, computed client-side; covered by a parity test.
 * Mirrors the Python exactly: population std for the information ratio (per-decision,
 * NOT annualized — unlike portfolio-risk-metrics.ts's √252 Sharpe), sortino falling
 * back to the info ratio when there is no downside, max drawdown over the compounded
 * decision equity curve. Bucket thresholds match lib/decision-scorecard.ts.
 */
export interface ConvictionBucketStat {
  conviction: number; // representative: high→5, medium→3, low→1 (monotone x-axis)
  mean_alpha_pct: number;
  n: number;
}
export interface DecisionTrackRecord {
  n_trades: number;
  hit_rate: number;
  mean_alpha_pct: number;
  median_alpha_pct: number;
  information_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  conviction_buckets: ConvictionBucketStat[];
}
export interface DecisionInput {
  run_date: string;
  return_frac: number;
  benchmark_frac: number;
  conviction: number | null;
  holding_days: number | null;
}

const HIGH_CONVICTION = 4;
const MED_CONVICTION = 2;

function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
}
function median(xs: number[]): number {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}
function std(xs: number[]): number {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  return Math.sqrt(xs.reduce((s, x) => s + (x - m) ** 2, 0) / xs.length);
}
function downsideStd(xs: number[]): number {
  if (xs.length < 2) return 0;
  return Math.sqrt(xs.reduce((s, x) => s + Math.min(0, x) ** 2, 0) / xs.length);
}
function maxDrawdownPct(returns: number[]): number {
  let nav = 1;
  let peak = 1;
  let worst = 0;
  for (const r of returns) {
    nav *= 1 + r;
    peak = Math.max(peak, nav);
    if (peak > 0) worst = Math.min(worst, nav / peak - 1);
  }
  return round4(worst * 100);
}
function round4(x: number): number {
  return Math.round(x * 1e4) / 1e4;
}
type Bucket = 'high' | 'medium' | 'low';
function bucketFor(conviction: number): Bucket {
  const mag = Math.abs(conviction);
  if (mag >= HIGH_CONVICTION) return 'high';
  if (mag >= MED_CONVICTION) return 'medium';
  return 'low';
}
const BUCKET_REP: Record<Bucket, number> = { high: 5, medium: 3, low: 1 };

function bucketStats(inputs: DecisionInput[]): ConvictionBucketStat[] {
  const order: Bucket[] = ['low', 'medium', 'high'];
  const grouped: Record<Bucket, number[]> = { low: [], medium: [], high: [] };
  for (const t of inputs) {
    if (t.conviction == null) continue;
    grouped[bucketFor(t.conviction)].push(t.return_frac - t.benchmark_frac);
  }
  const out: ConvictionBucketStat[] = [];
  for (const b of order) {
    const alphas = grouped[b];
    if (!alphas.length) continue;
    out.push({ conviction: BUCKET_REP[b], mean_alpha_pct: round4(mean(alphas) * 100), n: alphas.length });
  }
  return out;
}

export function backtestDecisions(inputs: DecisionInput[]): DecisionTrackRecord {
  if (!inputs.length) {
    return {
      n_trades: 0,
      hit_rate: 0,
      mean_alpha_pct: 0,
      median_alpha_pct: 0,
      information_ratio: 0,
      sortino_ratio: 0,
      max_drawdown_pct: 0,
      conviction_buckets: [],
    };
  }
  const ordered = [...inputs].sort((a, b) => a.run_date.localeCompare(b.run_date));
  const rets = ordered.map((t) => t.return_frac);
  const alphas = ordered.map((t) => t.return_frac - t.benchmark_frac);
  const stdA = std(alphas);
  const dstdA = downsideStd(alphas);
  const infoRatio = stdA > 0 ? round4(mean(alphas) / stdA) : 0;
  const sortino = dstdA > 0 ? round4(mean(alphas) / dstdA) : infoRatio;
  return {
    n_trades: ordered.length,
    hit_rate: round4(alphas.filter((a) => a > 0).length / alphas.length),
    mean_alpha_pct: round4(mean(alphas) * 100),
    median_alpha_pct: round4(median(alphas) * 100),
    information_ratio: infoRatio,
    sortino_ratio: sortino,
    max_drawdown_pct: maxDrawdownPct(rets),
    conviction_buckets: bucketStats(ordered),
  };
}
