/**
 * Pure derivation for the Decisions view: analysis periods, the cumulative
 * decision-edge trend, per-stance and per-conviction edge, the review queue and
 * the verdict. No React, no I/O. Alpha inputs are fractions; outputs are percent.
 */
import type { TableRow } from './database.types';
import {
  scoredDecisionEpisodes,
  type DecisionRecord,
  type DecisionScorecard,
  type ScoredDecisionEpisode,
} from './decision-scorecard';

export type AnalysisPeriod = '1w' | '1m' | '3m' | 'ytd' | '1y' | 'all';

export const ANALYSIS_PERIODS: ReadonlyArray<{ value: AnalysisPeriod; label: string }> = [
  { value: '1w', label: '1W' },
  { value: '1m', label: '1M' },
  { value: '3m', label: '3M' },
  { value: 'ytd', label: 'YTD' },
  { value: '1y', label: '1Y' },
  { value: 'all', label: 'All history' },
];

export function latestDecisionDate(decisions: readonly { run_date?: string | null }[]): string | null {
  return decisions.reduce<string | null>(
    (latest, d) => (d.run_date && (!latest || d.run_date > latest) ? d.run_date : latest),
    null
  );
}

export function earliestDecisionDate(decisions: readonly { run_date?: string | null }[]): string | null {
  return decisions.reduce<string | null>(
    (earliest, d) => (d.run_date && (!earliest || d.run_date < earliest) ? d.run_date : earliest),
    null
  );
}

function periodStart(period: AnalysisPeriod, asOf: string | null): string | null {
  if (period === 'all' || !asOf) return null;
  if (period === 'ytd') return `${asOf.slice(0, 4)}-01-01`;
  const start = new Date(`${asOf}T00:00:00Z`);
  if (period === '1w') {
    start.setUTCDate(start.getUTCDate() - 7);
    return start.toISOString().slice(0, 10);
  }
  const day = start.getUTCDate();
  start.setUTCDate(1);
  if (period === '1m') start.setUTCMonth(start.getUTCMonth() - 1);
  if (period === '3m') start.setUTCMonth(start.getUTCMonth() - 3);
  if (period === '1y') start.setUTCFullYear(start.getUTCFullYear() - 1);
  const lastDay = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0)).getUTCDate();
  start.setUTCDate(Math.min(day, lastDay));
  return start.toISOString().slice(0, 10);
}

/** Decisions inside the period, measured back from the latest decision date. */
export function filterDecisionsByPeriod(
  decisions: TableRow<'decision_log'>[],
  period: AnalysisPeriod
): TableRow<'decision_log'>[] {
  const start = periodStart(period, latestDecisionDate(decisions));
  return start ? decisions.filter((d) => d.run_date >= start) : decisions;
}

/** Scored episodes that start inside the period, plus pending calls in it. */
export function decisionsForAnalysisPeriod(
  decisions: TableRow<'decision_log'>[],
  period: AnalysisPeriod
): DecisionRecord[] {
  const start = periodStart(period, latestDecisionDate(decisions));
  const scored = scoredDecisionEpisodes(decisions)
    .filter((item) => !start || (item.decision.run_date ?? '') >= start)
    .map((item) => item.decision);
  const pending = filterDecisionsByPeriod(decisions, period).filter((d) => d.status === 'pending');
  return [...scored, ...pending];
}

export interface DecisionEdgePoint {
  date: string;
  /** Cumulative mean decision edge, percent. */
  value: number;
}

export function buildDecisionEdgeTrend(episodes: ScoredDecisionEpisode[]): DecisionEdgePoint[] {
  const sorted = [...episodes].sort((a, b) =>
    (a.decision.run_date ?? '').localeCompare(b.decision.run_date ?? '')
  );
  const byDate = new Map<string, DecisionEdgePoint>();
  let cumulative = 0;
  let count = 0;
  for (const episode of sorted) {
    const date = episode.decision.run_date;
    if (!date) continue;
    cumulative += episode.directionalAlpha;
    count += 1;
    byDate.set(date, { date, value: (cumulative / count) * 100 });
  }
  return [...byDate.values()];
}

export interface StanceEdge {
  stance: string;
  n: number;
  meanAlphaPct: number;
  hitRatePct: number;
}

export function stanceEdges(episodes: ScoredDecisionEpisode[]): StanceEdge[] {
  const groups = new Map<string, number[]>();
  for (const e of episodes) {
    const stance = e.decision.stance?.trim().toLowerCase() || 'unknown';
    groups.set(stance, [...(groups.get(stance) ?? []), e.directionalAlpha]);
  }
  return [...groups.entries()]
    .map(([stance, alphas]) => ({
      stance,
      n: alphas.length,
      meanAlphaPct: (alphas.reduce((s, a) => s + a, 0) / alphas.length) * 100,
      hitRatePct: (alphas.filter((a) => a > 0).length / alphas.length) * 100,
    }))
    .sort((a, b) => b.n - a.n);
}

/** The n scored decisions with the lowest directional edge, worst first. */
export function reviewQueue(episodes: ScoredDecisionEpisode[], n = 5): ScoredDecisionEpisode[] {
  return [...episodes].sort((a, b) => a.directionalAlpha - b.directionalAlpha).slice(0, n);
}

export type EdgeVerdictTone = 'accent' | 'warn' | 'mute';

/** Health vocabulary (accent / warn / ink-mute); the sign is also spelled out. */
export function edgeVerdict(meanAlphaPct: number | null): { label: string; tone: EdgeVerdictTone } {
  if (meanAlphaPct == null || !Number.isFinite(meanAlphaPct)) {
    return { label: 'Awaiting resolved outcomes', tone: 'mute' };
  }
  if (meanAlphaPct > 0) return { label: 'Positive decision edge', tone: 'accent' };
  if (meanAlphaPct < 0) return { label: 'Negative decision edge', tone: 'warn' };
  return { label: 'No measured decision edge', tone: 'mute' };
}

export function sampleLabel(nScored: number): string {
  if (nScored >= 50) return 'larger sample';
  if (nScored >= 20) return 'moderate sample';
  return 'limited sample';
}

export interface ConvictionEdgeBar {
  bucket: 'low' | 'medium' | 'high';
  meanAlphaPct: number | null;
  n: number;
}

/** Always three rows (low / medium / high); a missing bucket is null, never a fabricated 0. */
export function convictionEdgeBars(scorecard: DecisionScorecard): ConvictionEdgeBar[] {
  return (['low', 'medium', 'high'] as const).map((bucket) => {
    const row = scorecard.buckets.find((b) => b.bucket === bucket);
    return { bucket, meanAlphaPct: row ? row.meanAlphaPct : null, n: row?.n ?? 0 };
  });
}
