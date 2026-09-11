/**
 * Decision scorecard — conviction calibration for the Observability dashboard (Pillar 3D).
 *
 * Pure functions over resolved `decision_log` rows. The central question: do **higher-
 * conviction** calls earn **higher alpha**? `alpha` is the realized excess return over the
 * benchmark (SPY) computed at resolution time, stored as a FRACTION (0.05 = +5%); we surface
 * percent points.
 *
 * Conviction domain: `decision_log.conviction` maps to `AnalystPayload.conviction_score`
 * which is `ge=-5 le=5` — the full range is `[-5, +5]`, NOT `[0..5]`.  A sell-side call
 * recorded as −4 is high-conviction (short/exit) and must not be bucketed as "low".
 * Buckets are therefore applied to |conviction| (the magnitude):
 *
 *   high   |conv| ≥ 4
 *   medium |conv| ≥ 2
 *   low    |conv| < 2
 *
 * This matches the Python backtest core (digiquant/…/research/backtest.py
 * `_HIGH_CONVICTION` / `_MED_CONVICTION`) — both sides of the sign axis use the same
 * thresholds so the in-graph backtest and this dashboard agree.
 */

/** Conviction magnitude thresholds — kept in sync with backtest.py. */
const HIGH_CONVICTION = 4;
const MED_CONVICTION = 2;

export type ConvictionBucket = 'low' | 'medium' | 'high';

/** Minimal shape consumed from a `decision_log` row (alpha is a fraction). */
export interface DecisionRecord {
  id?: string;
  conviction: number | null;
  alpha: number | null;
  actual_return?: number | null;
  status: string;
  stance?: string | null;
  ticker?: string | null;
  run_date?: string | null; // ISO date string
  holding_days?: number | null;
  thesis?: string | null;
  reflection?: string | null;
}

export type DecisionDirection = 'bullish' | 'bearish';

/** Map a recorded stance onto the direction used to score excess return. */
export function decisionDirection(stance?: string | null): DecisionDirection | null {
  if (!stance) return null;
  const s = stance.toLowerCase().trim();
  if (['buy', 'add', 'hold', 'bullish', 'long'].includes(s)) return 'bullish';
  if (['sell', 'trim', 'avoid', 'bearish', 'short'].includes(s)) return 'bearish';
  return null;
}

/** Raw alpha for bullish calls, negated raw alpha for bearish calls. */
export function directionAdjustedAlpha(alpha: number, stance?: string | null): number | null {
  const dir = decisionDirection(stance);
  if (dir === 'bullish') return alpha;
  if (dir === 'bearish') return -alpha;
  return null;
}

/**
 * Collapse resolved same-ticker same-normalized-direction decisions into headline episodes.
 * When forward windows overlap (using run_date + holding_days), preserve the earliest
 * initiating row. Start a new episode on stance/direction change or non-overlap.
 * Returns collapsed episodes as DecisionRecords (preserves earliest row's data).
 */
export function collapseIntoEpisodes(decisions: DecisionRecord[]): DecisionRecord[] {
  const scorable = decisions.filter((d) => {
    if (!hasResolvedAlpha(d)) return false;
    const dirAlpha = directionAdjustedAlpha(d.alpha, d.stance);
    if (dirAlpha === null) return false;
    return d.ticker && d.run_date && d.holding_days != null;
  });

  if (!scorable.length) return [];

  // Repeated observations only share an episode when their recorded stance is unchanged.
  const grouped = new Map<string, DecisionRecord[]>();
  for (const d of scorable) {
    const stance = d.stance?.trim().toLowerCase();
    const key = `${d.ticker?.trim().toUpperCase()}|${stance}`;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(d);
  }

  const episodes: DecisionRecord[] = [];

  for (const group of grouped.values()) {
    group.sort((a, b) => a.run_date!.localeCompare(b.run_date!));

    let currentEpisode = group[0];
    let episodeEnd = addDays(currentEpisode.run_date!, currentEpisode.holding_days!);

    for (let i = 1; i < group.length; i++) {
      const next = group[i];
      const nextStart = next.run_date!;

      if (nextStart < episodeEnd) {
        const nextEnd = addDays(nextStart, next.holding_days!);
        if (nextEnd > episodeEnd) {
          episodeEnd = nextEnd;
        }
      } else {
        episodes.push(currentEpisode);
        currentEpisode = next;
        episodeEnd = addDays(next.run_date!, next.holding_days!);
      }
    }
    episodes.push(currentEpisode);
  }

  return episodes.sort((a, b) => (a.run_date ?? '').localeCompare(b.run_date ?? ''));
}

/** Add days to an ISO date string, returning ISO date string. */
function addDays(dateStr: string, days: number): string {
  const d = new Date(dateStr + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().split('T')[0];
}

export interface BucketCalibration {
  bucket: ConvictionBucket;
  n: number;
  meanAlphaPct: number;
  hitRatePct: number; // share of decisions with alpha > 0 (0..100)
  meanConviction: number;
}

export interface DecisionScorecard {
  nResolved: number;
  nPending: number;
  hitRatePct: number; // overall share with positive alpha (0..100)
  meanAlphaPct: number;
  medianAlphaPct: number;
  informationRatio: number; // mean alpha / std dev of alphas
  buckets: BucketCalibration[]; // present buckets, ascending conviction (low → high)
  /** True when mean alpha is non-decreasing across present buckets (the calibration we want). */
  calibrated: boolean;
  /** Evidence state for conviction calibration: insufficient, aligned, or inverted. */
  calibrationEvidence: 'insufficient' | 'aligned' | 'inverted';
}

export interface ScoredDecisionEpisode {
  decision: DecisionRecord;
  direction: DecisionDirection;
  directionalAlpha: number;
}

function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
}

function median(xs: number[]): number {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function stdDev(xs: number[]): number {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  const variance = xs.reduce((sum, x) => sum + (x - m) ** 2, 0) / xs.length;
  return Math.sqrt(variance);
}

function round4(x: number): number {
  return Math.round(x * 1e4) / 1e4;
}

/**
 * Map a conviction value to a calibration bucket.
 * Uses |conviction| (magnitude) so that sell-side calls (negative values) are
 * bucketed symmetrically with buy-side calls of equal strength.
 */
export function bucketFor(conviction: number): ConvictionBucket {
  const mag = Math.abs(conviction);
  if (mag >= HIGH_CONVICTION) return 'high';
  if (mag >= MED_CONVICTION) return 'medium';
  return 'low';
}

/** A resolved decision with a realized alpha scores the overall track record (conviction optional). */
function hasResolvedAlpha(d: DecisionRecord): d is DecisionRecord & { alpha: number } {
  return d.status === 'resolved' && d.alpha != null;
}

/** Calibration additionally needs a recorded conviction to place the row in a bucket. */
function isCalibratable(
  d: DecisionRecord
): d is DecisionRecord & { conviction: number; alpha: number } {
  return hasResolvedAlpha(d) && d.conviction != null;
}

/** Per-bucket calibration over resolved decisions, ascending conviction; empty buckets omitted. */
export function convictionBucketCalibration(decisions: DecisionRecord[]): BucketCalibration[] {
  const order: ConvictionBucket[] = ['low', 'medium', 'high'];
  const grouped: Record<ConvictionBucket, { alphas: number[]; convs: number[] }> = {
    low: { alphas: [], convs: [] },
    medium: { alphas: [], convs: [] },
    high: { alphas: [], convs: [] },
  };
  for (const d of decisions) {
    if (!isCalibratable(d)) continue;
    const dirAlpha = directionAdjustedAlpha(d.alpha, d.stance);
    if (dirAlpha === null) continue;
    const g = grouped[bucketFor(d.conviction)];
    g.alphas.push(dirAlpha);
    g.convs.push(d.conviction);
  }
  const out: BucketCalibration[] = [];
  for (const bucket of order) {
    const { alphas, convs } = grouped[bucket];
    if (!alphas.length) continue;
    out.push({
      bucket,
      n: alphas.length,
      meanAlphaPct: round4(mean(alphas) * 100),
      hitRatePct: round4((alphas.filter((a) => a > 0).length / alphas.length) * 100),
      meanConviction: round4(mean(convs)),
    });
  }
  return out;
}

/** Scored headline observations, collapsed when all eligible rows carry episode fields. */
export function scoredDecisionEpisodes(decisions: DecisionRecord[]): ScoredDecisionEpisode[] {
  const eligible = decisions.filter((d) => {
    return hasResolvedAlpha(d) && directionAdjustedAlpha(d.alpha, d.stance) !== null;
  });
  const canCollapse = eligible.every(
    (d) => d.ticker != null && d.run_date != null && d.holding_days != null
  );
  const episodeRows = canCollapse ? collapseIntoEpisodes(eligible) : eligible;

  return episodeRows.flatMap((decision) => {
    if (decision.alpha == null) return [];
    const direction = decisionDirection(decision.stance);
    const directionalAlpha = directionAdjustedAlpha(decision.alpha, decision.stance);
    return direction && directionalAlpha != null
      ? [{ decision, direction, directionalAlpha }]
      : [];
  });
}

/** Overall scorecard; null when there are no resolved decisions to score. */
export function computeDecisionScorecard(decisions: DecisionRecord[]): DecisionScorecard | null {
  const episodes = scoredDecisionEpisodes(decisions);
  if (!episodes.length) return null;
  const alphas = episodes.map((episode) => episode.directionalAlpha);
  const buckets = convictionBucketCalibration(episodes.map((episode) => episode.decision));

  // Calibrated = mean alpha never falls as conviction rises across the present buckets.
  let calibrated = true;
  for (let i = 1; i < buckets.length; i++) {
    if (buckets[i].meanAlphaPct < buckets[i - 1].meanAlphaPct) {
      calibrated = false;
      break;
    }
  }

  const std = stdDev(alphas);
  const informationRatio = std > 0 ? round4(mean(alphas) / std) : 0;

  let calibrationEvidence: 'insufficient' | 'aligned' | 'inverted';
  const sufficientBuckets = buckets.filter((b) => b.n >= 10);
  if (sufficientBuckets.length < 2) {
    calibrationEvidence = 'insufficient';
  } else {
    calibrationEvidence = 'aligned';
    for (let i = 1; i < sufficientBuckets.length; i++) {
      if (sufficientBuckets[i].meanAlphaPct < sufficientBuckets[i - 1].meanAlphaPct) {
        calibrationEvidence = 'inverted';
        break;
      }
    }
  }

  return {
    nResolved: episodes.length,
    nPending: decisions.filter((d) => d.status === 'pending').length,
    hitRatePct: round4((alphas.filter((a) => a > 0).length / alphas.length) * 100),
    meanAlphaPct: round4(mean(alphas) * 100),
    medianAlphaPct: round4(median(alphas) * 100),
    informationRatio,
    buckets,
    calibrated,
    calibrationEvidence,
  };
}
