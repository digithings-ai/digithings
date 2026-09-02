/**
 * H7 PM direction operator surface (WP-G).
 *
 * Rank is ordinal order, not size. Confidence is how sure the PM is of the name
 * ([0, 1], shown as a percent). Buy/hold/sell is derived from prior vs H8
 * target when a rebalance payload is at hand, else from prior direction, else
 * the raw long/flat label. Audit fields (forecast_reference, degradation_reason)
 * are never copied into the operator row.
 */

export type PmDirection = 'long' | 'flat';
export type PmAction = 'buy' | 'hold' | 'sell' | 'long' | 'flat';

export type PmDirectionRow = {
  ticker: string;
  direction: PmDirection;
  convictionRank: number;
  narrative: string | null;
  confidence: number | null;
};

export type ParsedPmDirectionMemo = {
  date: string | null;
  memo: string | null;
  roster: PmDirectionRow[];
};

export type PmRebalanceSlice = {
  action?: string;
  currentPct?: number;
  targetPct?: number;
};

export type PmActionContext = {
  priorByTicker: Record<string, PmDirection>;
  rebalanceByTicker: Record<string, PmRebalanceSlice>;
};

const WEIGHT_EPS = 0.01;

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function asFiniteNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return undefined;
}

function asDirection(value: unknown): PmDirection | null {
  if (value === 'long' || value === 'flat') return value;
  if (typeof value === 'string') {
    const lower = value.trim().toLowerCase();
    if (lower === 'long' || lower === 'flat') return lower;
  }
  return null;
}

function tickerKey(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const t = value.trim().toUpperCase();
  return t || null;
}

export function parsePmDirectionMemo(payload: unknown): ParsedPmDirectionMemo {
  const body = asRecord(payload);
  if (!body) return { date: null, memo: null, roster: [] };

  const date = typeof body.date === 'string' && body.date.trim() ? body.date.trim() : null;
  const memo = typeof body.memo === 'string' && body.memo.trim() ? body.memo.trim() : null;
  const rawRoster = Array.isArray(body.roster) ? body.roster : [];
  const roster: PmDirectionRow[] = [];

  for (const entry of rawRoster) {
    const row = asRecord(entry);
    if (!row) continue;
    const ticker = tickerKey(row.ticker);
    const direction = asDirection(row.direction);
    const rank = asFiniteNumber(row.conviction_rank);
    if (!ticker || !direction || rank == null || rank < 1) continue;
    const narrative =
      typeof row.narrative === 'string' && row.narrative.trim() ? row.narrative.trim() : null;
    const confidenceRaw = asFiniteNumber(row.confidence);
    const confidence =
      confidenceRaw != null && confidenceRaw >= 0 && confidenceRaw <= 1 ? confidenceRaw : null;
    roster.push({
      ticker,
      direction,
      convictionRank: Math.trunc(rank),
      narrative,
      confidence,
    });
  }

  return { date, memo, roster };
}

export function sortPmRoster(rows: PmDirectionRow[]): PmDirectionRow[] {
  return [...rows].sort((a, b) => {
    if (a.direction !== b.direction) return a.direction === 'long' ? -1 : 1;
    if (a.convictionRank !== b.convictionRank) return a.convictionRank - b.convictionRank;
    return a.ticker.localeCompare(b.ticker);
  });
}

export function formatPmConfidence(confidence: number | null | undefined): string {
  if (confidence == null || !Number.isFinite(confidence)) return '—';
  return `${Math.round(confidence * 100)}%`;
}

export function labelPmAction(action: PmAction): string {
  switch (action) {
    case 'buy':
      return 'Buy';
    case 'hold':
      return 'Hold';
    case 'sell':
      return 'Sell';
    case 'long':
      return 'Long';
    case 'flat':
      return 'Flat';
    default: {
      const _exhaustive: never = action;
      return _exhaustive;
    }
  }
}

function mapRebalanceVerb(action: string | undefined): PmAction | null {
  if (!action) return null;
  switch (action.trim().toLowerCase()) {
    case 'new':
    case 'add':
      return 'buy';
    case 'hold':
    case 'trim':
      return 'hold';
    case 'exit':
      return 'sell';
    default:
      return null;
  }
}

export function derivePmAction(input: {
  direction: PmDirection;
  priorDirection?: PmDirection | null;
  priorWeightPct?: number | null;
  targetWeightPct?: number | null;
  rebalanceAction?: string | null;
}): PmAction {
  const fromVerb = mapRebalanceVerb(input.rebalanceAction ?? undefined);
  if (fromVerb) return fromVerb;

  const hasWeights =
    typeof input.priorWeightPct === 'number' || typeof input.targetWeightPct === 'number';
  if (hasWeights) {
    const prior = typeof input.priorWeightPct === 'number' ? input.priorWeightPct : 0;
    const target = typeof input.targetWeightPct === 'number' ? input.targetWeightPct : 0;
    if (target <= WEIGHT_EPS && prior > WEIGHT_EPS) return 'sell';
    if (target > prior + WEIGHT_EPS) return 'buy';
    return 'hold';
  }

  if (input.priorDirection === 'long' || input.priorDirection === 'flat') {
    if (input.direction === 'long' && input.priorDirection === 'flat') return 'buy';
    if (input.direction === 'flat' && input.priorDirection === 'long') return 'sell';
    return 'hold';
  }

  return input.direction;
}

export function priorByTickerFromRoster(
  priorRoster: Array<{ ticker: string; direction: string }> | undefined,
): Record<string, PmDirection> {
  const out: Record<string, PmDirection> = {};
  if (!priorRoster) return out;
  for (const row of priorRoster) {
    const ticker = tickerKey(row.ticker);
    const direction = asDirection(row.direction);
    if (!ticker || !direction) continue;
    out[ticker] = direction;
  }
  return out;
}

export function rebalanceByTickerFromPayload(
  rebalance: Record<string, unknown> | null | undefined,
): Record<string, PmRebalanceSlice> {
  const out: Record<string, PmRebalanceSlice> = {};
  const body = asRecord(rebalance);
  if (!body) return out;

  const merge = (ticker: string, slice: PmRebalanceSlice) => {
    const prev = out[ticker] ?? {};
    out[ticker] = {
      action: slice.action ?? prev.action,
      currentPct: slice.currentPct ?? prev.currentPct,
      targetPct: slice.targetPct ?? prev.targetPct,
    };
  };

  const actions = Array.isArray(body.actions) ? body.actions : [];
  for (const raw of actions) {
    const row = asRecord(raw);
    if (!row) continue;
    const ticker = tickerKey(row.ticker);
    if (!ticker) continue;
    merge(ticker, {
      action: typeof row.action === 'string' ? row.action : undefined,
      currentPct: asFiniteNumber(row.current_pct),
      targetPct: asFiniteNumber(row.target_pct) ?? asFiniteNumber(row.recommended_pct),
    });
  }

  const weights = Array.isArray(body.recommended_portfolio) ? body.recommended_portfolio : [];
  for (const raw of weights) {
    const row = asRecord(raw);
    if (!row) continue;
    const ticker = tickerKey(row.ticker);
    if (!ticker) continue;
    merge(ticker, {
      targetPct: asFiniteNumber(row.target_pct) ?? asFiniteNumber(row.weight_pct),
    });
  }

  return out;
}

export function actionForRow(row: PmDirectionRow, context: PmActionContext): PmAction {
  const key = row.ticker.toUpperCase();
  const slice = context.rebalanceByTicker[key];
  return derivePmAction({
    direction: row.direction,
    priorDirection: context.priorByTicker[key] ?? null,
    priorWeightPct: slice?.currentPct,
    targetWeightPct: slice?.targetPct,
    rebalanceAction: slice?.action,
  });
}

export function buildPmActionContext(input: {
  priorRoster?: Array<{ ticker: string; direction: string }>;
  rebalance?: Record<string, unknown> | null;
}): PmActionContext {
  return {
    priorByTicker: priorByTickerFromRoster(input.priorRoster),
    rebalanceByTicker: rebalanceByTickerFromPayload(input.rebalance),
  };
}
