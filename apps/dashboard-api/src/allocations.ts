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
 * Weights: `weight_pct` is the book's own weight, anchored to the
 * `position_events` ledger when the ledger covers the ticker (DIG-2803);
 * `scaled_weight_pct` is that weight rescaled into the §6.1 envelope
 * (`invested / heldSum`). The raw `positions.weight_pct` is always reported
 * alongside as `positions_weight_pct` so the anchoring never hides drift.
 *
 * Pure logic — the route layer supplies book rows + optional market closes and
 * an optional replayed ledger. No I/O, no secrets, no time/tool-call budgets.
 */

import { reconcileBook, type BookPositionInput } from './book';
import {
  reconcileWeightsAgainstLedger,
  type LedgerWeightState,
  type WeightSource,
} from './ledger-weights';

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
  /** Raw `positions.weight_pct`; preserved even when `weightPct` is
   *  ledger-anchored, so the substitution stays measurable. */
  positionsWeightPct: number;
  weightSource: WeightSource;
  ledgerWeightPct: number | null;
  /** `positions_weight_pct - ledger_weight_pct`; null when not covered. */
  weightDriftPp: number | null;
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
  /** Latest `position_events.date` applied, or null when no ledger was read. */
  ledgerAsOf: string | null;
  /** Tickers whose emitted weight came from the ledger. */
  weightsReconciled: number;
  /** Of those, how many disagree with the positions rows. */
  weightsDrifted: number;
  /** Book rows the ledger has EXITed. */
  ledgerConflicts: string[];
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
 *
 * When `ledgerState` is supplied and covers at least one ticker, each covered
 * row's weight is the ledger target and the reconciliation runs BEFORE
 * `reconcileBook`, so `heldSum`, `scale` and therefore `scaled_weight_pct`
 * reflect the ledger-anchored book. With `ledgerState` null (or a ledger that
 * covers nothing) the emitted payload is byte-identical to the pre-DIG-2803
 * shape.
 */
export function buildAllocationsData(args: {
  positions: ReadonlyArray<AllocationPositionInput>;
  resolvedInvestedPct: number | null;
  marketCloses?: ReadonlyMap<string, MarketCloseFill>;
  ledgerState?: LedgerWeightState | null;
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
  const weights = reconcileWeightsAgainstLedger(deduped, args.ledgerState ?? null);
  // Ledger-anchored rows feed the envelope; untouched rows keep their own.
  const bookRows: AllocationPositionInput[] = deduped.map((p) => {
    const w = weights.resolved.get(p.ticker);
    return w && w.weightSource === 'ledger' ? { ...p, weightActual: w.weightPct } : p;
  });
  const book = reconcileBook(bookRows, { investedPct: args.resolvedInvestedPct });
  const scaledByTicker = new Map(book.rows.map((r) => [r.ticker, r.scaledWeightPct]));
  const rows: AllocationRow[] = deduped.map((p) => {
    const w = weights.resolved.get(p.ticker) ?? {
      ticker: p.ticker,
      positionsWeightPct: p.weightActual ?? 0,
      weightPct: p.weightActual ?? 0,
      weightSource: 'positions_no_ledger' as const,
      ledgerWeightPct: null,
      driftPp: null,
    };
    return {
      ticker: p.ticker,
      weightPct: w.weightPct,
      scaledWeightPct: scaledByTicker.get(p.ticker) ?? 0,
      positionsWeightPct: w.positionsWeightPct,
      weightSource: w.weightSource,
      ledgerWeightPct: w.ledgerWeightPct,
      weightDriftPp: w.driftPp,
      ...resolveRowValuation(p, args.marketCloses?.get(p.ticker)),
    };
  });
  const marksUnstamped =
    deduped.length === 0 ||
    deduped.some((p) => p.metricsAsOf == null || String(p.metricsAsOf).trim() === '');
  return {
    investedPct: book.investedPct,
    cashPct: book.cashPct,
    rows,
    marksUnstamped,
    ledgerAsOf: weights.state?.latestEventDate ?? null,
    weightsReconciled: weights.reconciledCount,
    weightsDrifted: weights.driftedCount,
    ledgerConflicts: weights.conflicts,
  };
}
