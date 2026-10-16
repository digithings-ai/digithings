/**
 * Stretch: do currently-divergent currencies score differently on the 5-day
 * consensus accuracy read? Joins the live divergent flags in
 * `divergenceByCurrency` against scored `fx_consensus_eval` rows (same
 * timeframe/weighted pin as `summarizeConsensusAccuracy`) and returns one
 * Wilson interval per bucket. Descriptive, not causal — the flag is current
 * while the scored rows span history.
 */
import { wilsonInterval, type WilsonInterval } from './wilson';
import type { FxConsensusDivergence, FxConsensusEvalRow } from './types';

export interface DivergenceAccuracySummary {
  divergent: WilsonInterval;
  aligned: WilsonInterval;
}

export function summarizeDivergenceAccuracy(
  divergenceByCurrency: Record<string, FxConsensusDivergence>,
  rows: FxConsensusEvalRow[],
): DivergenceAccuracySummary {
  let divK = 0;
  let divN = 0;
  let aliK = 0;
  let aliN = 0;
  for (const r of rows) {
    if (r.timeframe !== 'medium' || r.weighted !== true) continue;
    if (r.accuracy_status !== 'scored') continue;
    if (r.hit_5d === null || r.hit_5d === undefined) continue;
    const divergent = divergenceByCurrency[r.currency]?.isDivergent === true;
    if (divergent) {
      divN += 1;
      if (r.hit_5d) divK += 1;
    } else {
      aliN += 1;
      if (r.hit_5d) aliK += 1;
    }
  }
  return {
    divergent: wilsonInterval(divK, divN),
    aligned: wilsonInterval(aliK, aliN),
  };
}
