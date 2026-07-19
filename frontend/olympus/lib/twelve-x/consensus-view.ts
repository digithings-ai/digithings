/**
 * The SINGLE shared consensus derivation for the twelve-x dashboard.
 *
 * The Today tab's "Consensus average" chart and the Consensus tab used to
 * duplicate the same three decisions inline — which currencies to show, in what
 * order, and how a score maps to a conviction word — and drifted apart. This
 * module is the one source of truth for all three so the two surfaces can never
 * visibly disagree:
 *   - FILTER: the caller passes the already-pinned (weighted, medium) score
 *     series; this rolls it up to exactly one row per currency.
 *   - ORDERING: `orderCurrencies` — the canonical G10 sequence, extras after.
 *   - SCORE → LABEL: the conviction word comes from the shared `scoreLabel`.
 *
 * It does NOT touch the underlying data model — it only reshapes rows the
 * fetch layer already returns.
 */

import { G10_CURRENCIES } from './types';
import type { FxConsensusSnapshotRow } from './types';
import { latestConsensusAverages, type ScorePoint } from './consensus-derive';
import { scoreLabel } from './consensus-bar';

/**
 * Canonical currency ordering shared by every consensus surface: the fixed G10
 * sequence first (USD, EUR, JPY, …), then any non-G10 extras alpha-sorted after.
 * Deduplicates its input, so it is safe to pass a raw list of `row.currency`.
 */
export function orderCurrencies(present: Iterable<string>): string[] {
  const set = new Set(present);
  const ordered = G10_CURRENCIES.filter((c) => set.has(c));
  const orderedSet = new Set<string>(ordered);
  const extras = [...set].filter((c) => !orderedSet.has(c)).sort();
  return [...ordered, ...extras];
}

/**
 * One per-currency consensus row: the trailing-average family (what the Today
 * chart headlines) plus the latest raw score and its conviction label (what the
 * Consensus tab headlines). Every consumer reads the same fields, so the two
 * tabs describe the same currency identically.
 */
export interface ConsensusCurrencyRow {
  currency: string;
  /** Trailing 5-run consensus average — the Today chart's headline value. */
  avgNow: number | null;
  /** Latest raw score for the currency — the Consensus table's headline value. */
  actualNow: number | null;
  /** Trailing average one run back (reference tick). */
  avgYesterday: number | null;
  /** Trailing average ~5 runs back (reference tick). */
  avgAgo: number | null;
  /** actualNow − avgNow: today's score vs its own trend (rate of change). */
  momentum: number | null;
  /** Conviction word from the latest raw score, via the shared `scoreLabel`. */
  label: string;
  /** Previous finite raw score (one run back) for prior-run comparison. */
  priorActual: number | null;
  /** Change from prior run: actualNow − priorActual. */
  priorChange: number | null;
}

/**
 * The shared per-currency consensus view-model, in canonical G10 order.
 *
 * For each currency present in `series`, gathers its points in ascending
 * run_date order and rolls them up via `latestConsensusAverages` (trailing-5
 * average family + momentum), then attaches the conviction `label` for the
 * latest raw score. Consumed by both the Today chart and the Consensus tab.
 */
export function deriveConsensusRows(series: FxConsensusSnapshotRow[]): ConsensusCurrencyRow[] {
  const currencies = orderCurrencies(series.map((r) => r.currency));
  return currencies.map((currency) => {
    const points: ScorePoint[] = series
      .filter((r) => r.currency === currency)
      .sort((a, b) => a.run_date.localeCompare(b.run_date))
      .map((r) => ({ score: r.score }));
    const { avgNow, actualNow, avgYesterday, avgAgo, momentum } = latestConsensusAverages(points);
    const labelScore = Number.isFinite(actualNow) ? (actualNow as number) : 0;

    // Derive priorActual and priorChange: prior is the previous finite raw score.
    let priorActual: number | null = null;
    let priorChange: number | null = null;
    if (points.length >= 2) {
      // Walk backward from the second-to-last point to find the most recent finite score.
      for (let i = points.length - 2; i >= 0; i--) {
        if (Number.isFinite(points[i].score)) {
          priorActual = points[i].score;
          break;
        }
      }
      if (priorActual !== null && Number.isFinite(actualNow)) {
        priorChange = (actualNow as number) - priorActual;
      }
    }

    return {
      currency,
      avgNow,
      actualNow,
      avgYesterday,
      avgAgo,
      momentum,
      label: scoreLabel(labelScore),
      priorActual,
      priorChange,
    };
  });
}
