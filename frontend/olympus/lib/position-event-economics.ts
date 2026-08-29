/**
 * Single-source trade economics for position_events (Ledger + Tearsheet).
 *
 * Realized % is fill price vs average entry as of the event date.
 * Sold weight is prev_weight − residual (EXIT may use prev alone).
 * Never invent fills or cost basis — fail closed to null.
 */

export type EntryPriceMark = {
  date: string;
  ticker: string;
  entry_price: number | null | undefined;
};

export type SellableEvent = {
  event: 'OPEN' | 'EXIT' | 'TRIM' | 'ADD' | 'HOLD' | string;
  weight_pct: number | null | undefined;
  prev_weight_pct: number | null | undefined;
  price: number | null | undefined;
};

function finitePositive(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value) || value <= 0) return null;
  return value;
}

export function roundPct(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}

/**
 * Average entry as of a realized event date: latest `entry_price` on or before
 * that date for the ticker. Sells do not change average cost.
 */
export function averageEntryAsOf(
  positions: readonly EntryPriceMark[],
  ticker: string,
  asOfDate: string
): number | null {
  const key = ticker.toUpperCase();
  let best: EntryPriceMark | null = null;
  for (const row of positions) {
    if (row.ticker.toUpperCase() !== key) continue;
    if (row.date > asOfDate) continue;
    if (finitePositive(row.entry_price) == null) continue;
    if (!best || row.date.localeCompare(best.date) > 0) best = row;
  }
  return finitePositive(best?.entry_price);
}

/** Weight sold on a TRIM/EXIT — fail closed without a usable weight delta. */
export function soldWeightPct(event: SellableEvent): number | null {
  const prev = event.prev_weight_pct;
  const residual = event.weight_pct;
  if (prev != null && Number.isFinite(prev) && residual != null && Number.isFinite(residual)) {
    const sold = prev - residual;
    return Number.isFinite(sold) ? roundPct(sold) : null;
  }
  if (event.event === 'EXIT' && prev != null && Number.isFinite(prev)) return roundPct(prev);
  return null;
}

export function realizedReturnVsAverageEntry(
  exitPrice: number | null | undefined,
  averageEntry: number | null
): number | null {
  const sell = finitePositive(exitPrice);
  const entry = finitePositive(averageEntry);
  if (sell == null || entry == null) return null;
  return roundPct((sell / entry - 1) * 100);
}

export type LedgerEventEconomics = {
  avgEntryPrice: number | null;
  fillPrice: number | null;
  soldWeightPct: number | null;
  realizedReturnPct: number | null;
};

/**
 * Compact economics for one ledger row. OPEN/ADD report fill as entry and leave
 * realized null; TRIM/EXIT compute realized vs average entry when both exist.
 */
export function ledgerEventEconomics(
  event: SellableEvent & { ticker: string; date: string },
  positions: readonly EntryPriceMark[]
): LedgerEventEconomics {
  const fillPrice = finitePositive(event.price);
  const isSell = event.event === 'TRIM' || event.event === 'EXIT';
  if (!isSell) {
    return {
      avgEntryPrice: fillPrice,
      fillPrice,
      soldWeightPct: null,
      realizedReturnPct: null,
    };
  }
  const avgEntryPrice = averageEntryAsOf(positions, event.ticker, event.date);
  return {
    avgEntryPrice,
    fillPrice,
    soldWeightPct: soldWeightPct(event),
    realizedReturnPct: realizedReturnVsAverageEntry(fillPrice, avgEntryPrice),
  };
}
