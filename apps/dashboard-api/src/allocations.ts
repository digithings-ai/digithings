/**
 * `GET /allocations` row builder for the dashboard-api worker (slice 0003).
 *
 * Consumes the same committed book as §6.1 and folds the `/valuations` read
 * into each row (contract §6.2): rows scale into the §6.1 envelope
 * (`invested = min(100, investedPct ?? heldSum)`, CASH excluded), and each
 * row carries its valuation mark.
 *
 * Valuation precedence mirrors the client (`apps/dashboard/README.md`,
 * `live-valuation.ts` close lane): prefer stored `unrealized_pnl_pct` /
 * `since_entry_return_pct`; else derive from `entry_price` vs `current_price`;
 * when the nightly metrics stamp is missing, fill the mark from the
 * caller-supplied market close (R2-API-only — empty when unset, no Supabase
 * fallback); fail closed to null without basis or mark. Mid-session NULL
 * marks affect marks only, never weights.
 *
 * Pure logic — the route layer supplies book rows + optional market closes.
 * No I/O, no secrets, no time/tool-call budgets.
 */

import { reconcileBook, type BookPositionInput } from './book';

export type MarkSource = 'stored' | 'market_api' | 'unavailable';

export interface AllocationPositionInput extends BookPositionInput {
  entryPrice?: number | null;
  currentPrice?: number | null;
  unrealizedPnlPct?: number | null;
  sinceEntryReturnPct?: number | null;
  /** Nightly metrics stamp; null/empty means the mark is unstamped. */
  metricsAsOf?: string | null;
}

/** Market-API close fill, keyed by ticker (R2-API-only; absent = no fill). */
export interface MarketCloseFill {
  price: number;
  asOf: string;
}

export interface AllocationRow {
  ticker: string;
  weightPct: number;
  scaledWeightPct: number;
  entryPrice: number | null;
  currentPrice: number | null;
  unrealizedPct: number | null;
  marks: MarkSource;
  marksAsOf: string | null;
}

export interface AllocationsData {
  investedPct: number;
  cashPct: number;
  rows: AllocationRow[];
  /** True when the open book is empty or any row lacks `metrics_as_of`. */
  marksUnstamped: boolean;
}

function finiteNum(v: number | null | undefined): number | null {
  return v != null && Number.isFinite(v) ? v : null;
}

/**
 * Resolve one row's valuation. `marketFill` is the `GET /v1/market/closes`
 * fill for this ticker (undefined = API empty or unconfigured — no fill).
 */
export function resolveRowValuation(
  position: AllocationPositionInput,
  marketFill?: MarketCloseFill,
): Pick<
  AllocationRow,
  'entryPrice' | 'currentPrice' | 'unrealizedPct' | 'marks' | 'marksAsOf'
> {
  const entryPrice = finiteNum(position.entryPrice);
  const stored = finiteNum(position.unrealizedPnlPct) ?? finiteNum(position.sinceEntryReturnPct);
  const closePrice = finiteNum(position.currentPrice);
  const stamped =
    position.metricsAsOf != null && String(position.metricsAsOf).trim() !== '';

  // Stored record first — never recompute over a number the nightly batch wrote.
  if (stored != null && closePrice != null && closePrice > 0 && stamped) {
    return {
      entryPrice,
      currentPrice: closePrice,
      unrealizedPct: stored,
      marks: 'stored',
      marksAsOf: position.metricsAsOf ?? null,
    };
  }
  // Derive from entry vs close when both legs exist (stored or market fill).
  const markPrice = closePrice ?? (stamped ? null : finiteNum(marketFill?.price));
  const markAsOf =
    closePrice != null && stamped
      ? (position.metricsAsOf ?? null)
      : !stamped
        ? (marketFill?.asOf ?? null)
        : null;
  if (entryPrice != null && entryPrice > 0 && markPrice != null && markPrice > 0) {
    const fromMarket = closePrice == null;
    if (fromMarket && marketFill == null) {
      return {
        entryPrice,
        currentPrice: null,
        unrealizedPct: null,
        marks: 'unavailable',
        marksAsOf: null,
      };
    }
    return {
      entryPrice,
      currentPrice: markPrice,
      unrealizedPct: ((markPrice - entryPrice) / entryPrice) * 100,
      marks: fromMarket ? 'market_api' : 'stored',
      marksAsOf: markAsOf,
    };
  }
  // Fail closed without basis or mark — never invent P&L.
  return {
    entryPrice,
    currentPrice: closePrice,
    unrealizedPct: null,
    marks: 'unavailable',
    marksAsOf: null,
  };
}

/**
 * Build the §6.2 payload rows. `resolvedInvestedPct` is the §6.1 resolution
 * (null when unavailable — envelope falls back to the held sum, capped 100).
 */
export function buildAllocationsData(args: {
  positions: ReadonlyArray<AllocationPositionInput>;
  resolvedInvestedPct: number | null;
  marketCloses?: ReadonlyMap<string, MarketCloseFill>;
}): AllocationsData {
  // Dedupe first with the same max-weight rule as `reconcileBook` so each
  // ticker's valuation comes from its kept row.
  const byTicker = new Map<string, AllocationPositionInput>();
  for (const p of args.positions) {
    if (p.ticker.trim().toUpperCase() === 'CASH') continue;
    const prev = byTicker.get(p.ticker);
    if (!prev || (p.weightActual ?? 0) > (prev.weightActual ?? 0)) {
      byTicker.set(p.ticker, p);
    }
  }
  const deduped = [...byTicker.values()];
  const book = reconcileBook(deduped, { investedPct: args.resolvedInvestedPct });
  const scaledByTicker = new Map(book.rows.map((r) => [r.ticker, r.scaledWeightPct]));
  const rows: AllocationRow[] = deduped.map((p) => ({
    ticker: p.ticker,
    weightPct: p.weightActual ?? 0,
    scaledWeightPct: scaledByTicker.get(p.ticker) ?? 0,
    ...resolveRowValuation(p, args.marketCloses?.get(p.ticker)),
  }));
  const marksUnstamped =
    deduped.length === 0 ||
    deduped.some((p) => p.metricsAsOf == null || String(p.metricsAsOf).trim() === '');
  return {
    investedPct: book.investedPct,
    cashPct: book.cashPct,
    rows,
    marksUnstamped,
  };
}
