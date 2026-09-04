import type { FxConsensusDivergence, FxConsensusSnapshotRow, FxTradeIdeaRow } from './types';

/** Default |street − pmt| gap above which the chip flags (spec R-5 — calibrate later). */
export const DEFAULT_DIVERGENCE_THRESHOLD = 1.0;

const SMART_BIAS_SLUG = 'smart-bias-tracker';

const SENTIMENT_SCORES: Record<string, number> = {
  'very bullish': 2,
  bullish: 1.25,
  'weak bullish': 0.75,
  neutral: 0,
  'weak bearish': -0.75,
  bearish: -1.25,
  'very bearish': -2,
};

function normalizeSentiment(raw: string): string {
  return raw.trim().toLowerCase().replace(/\s+/g, ' ');
}

/** Map PMT Smart Bias `Overall_Sentiment` onto the shared −2…+2 scale. */
export function mapSmartBiasSentiment(raw: string): number | null {
  const key = normalizeSentiment(raw);
  if (!key) return null;
  const score = SENTIMENT_SCORES[key];
  return score === undefined ? null : score;
}

/** Configurable divergence gap threshold (env override). */
export function divergenceThreshold(): number {
  const raw = process.env.NEXT_PUBLIC_TWELVEX_DIVERGENCE_THRESHOLD;
  const parsed = raw ? Number(raw) : DEFAULT_DIVERGENCE_THRESHOLD;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_DIVERGENCE_THRESHOLD;
}

function fmtSigned(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
}

export interface SmartBiasJoinRow {
  currency: string;
  overall_sentiment: string;
  week_first_date: string;
}

export interface MarketSnapshotJoin {
  id: string;
  payload: unknown;
}

function pickLatestBiasPerCurrency(rows: SmartBiasJoinRow[]): Map<string, SmartBiasJoinRow> {
  const byCcy = new Map<string, SmartBiasJoinRow>();
  for (const row of rows) {
    const ccy = row.currency.toUpperCase();
    const cur = byCcy.get(ccy);
    if (!cur || row.week_first_date > cur.week_first_date) {
      byCcy.set(ccy, { ...row, currency: ccy });
    }
  }
  return byCcy;
}

/**
 * PURE — join canonical consensus rows with the newest smart-bias read per currency.
 * Snapshot payload is attached from the weekly capture (same slug for all currencies).
 */
export function assembleConsensusDivergence(
  consensus: FxConsensusSnapshotRow[],
  biasRows: SmartBiasJoinRow[],
  snapshot: MarketSnapshotJoin | null,
  threshold: number = divergenceThreshold(),
): Record<string, FxConsensusDivergence> {
  const biasByCcy = pickLatestBiasPerCurrency(biasRows);
  const out: Record<string, FxConsensusDivergence> = {};

  for (const row of consensus) {
    const ccy = row.currency.toUpperCase();
    const bias = biasByCcy.get(ccy);
    if (!bias) continue;

    const pmtScore = mapSmartBiasSentiment(bias.overall_sentiment);
    if (pmtScore === null) continue;

    const consensusScore = row.score;
    const gap = Math.abs(consensusScore - pmtScore);
    const isDivergent = gap >= threshold;

    out[ccy] = {
      currency: ccy,
      consensusScore,
      consensusTilt: row.tilt,
      consensusAsOf: row.as_of,
      pmtSentiment: bias.overall_sentiment,
      pmtScore,
      pmtAsOf: bias.week_first_date,
      gap,
      isDivergent,
      snapshotId: snapshot?.id ?? null,
      rawSnapshot: snapshot?.payload ?? null,
      streetStatement: `Street score ${fmtSigned(consensusScore)} (tilt ${fmtSigned(row.tilt)})`,
      pmtStatement: `PMT Smart Bias Overall_Sentiment=${bias.overall_sentiment} (week of ${bias.week_first_date})`,
    };
  }

  return out;
}

/** Split a trade-idea pair into upper-case leg codes. */
export function pairCurrencies(pair: string): string[] {
  return pair
    .split('/')
    .map((leg) => leg.trim().toUpperCase())
    .filter((leg) => leg.length > 0);
}

export function isTradeIdeaDisputed(
  idea: FxTradeIdeaRow,
  byCurrency: Record<string, FxConsensusDivergence>,
): boolean {
  return pairCurrencies(idea.pair).some((ccy) => byCurrency[ccy]?.isDivergent === true);
}

export function countDisputedTradeIdeas(
  ideas: FxTradeIdeaRow[],
  byCurrency: Record<string, FxConsensusDivergence>,
): number {
  return ideas.filter((idea) => isTradeIdeaDisputed(idea, byCurrency)).length;
}

export function disputedTradeIdeaRanks(
  ideas: FxTradeIdeaRow[],
  byCurrency: Record<string, FxConsensusDivergence>,
): number[] {
  return ideas.filter((idea) => isTradeIdeaDisputed(idea, byCurrency)).map((idea) => idea.rank);
}

export { SMART_BIAS_SLUG };
