/**
 * Pure transforms for the live-price layer (#1461) — no React, no I/O, so they
 * are correct by inspection and unit-testable in isolation. The hooks
 * (useLivePrices / useLivePortfolio) wire these into effects; all price math
 * lives here.
 */
import type { LivePriceMap, LivePosition, LiveQuote, NavPoint } from "./types";

/** Coerce a supabase/PostgREST numeric (number OR decimal-string) → number | null. */
export function num(v: unknown): number | null {
  if (v == null) return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Normalize a symbol list: uppercase, de-duped, blanks dropped. */
export function normalizeSymbols(input: readonly string[] | undefined): string[] {
  if (!input) return [];
  const seen = new Set<string>();
  for (const s of input) {
    const t = s?.trim().toUpperCase();
    if (t) seen.add(t);
  }
  return [...seen];
}

/** Unix-seconds-or-ms → ms. Finnhub `t` is seconds; guard non-numbers. */
function toEpochMs(t: unknown, fallback: number): number {
  const n = num(t);
  if (n == null) return fallback;
  return n < 1e12 ? n * 1000 : n;
}

/**
 * A Postgres `timestamptz`, as Realtime delivers it off the WAL → epoch ms.
 *
 * Deliberately NOT {@link toEpochMs}. That one coerces through `num()`, which
 * turns any date STRING into `NaN` and then silently hands back the fallback —
 * every row would be stamped `Date.now()`, type-clean, lint-clean and wrong.
 * Postgres renders the column as `2026-08-01 14:23:00+00` (space separator,
 * two-digit offset); neither that nor a trailing bare offset is in the
 * ECMA-262 `Date.parse` grammar, so engines disagree about it. Try the value as
 * delivered, then once more normalized to strict ISO-8601, then give up —
 * `fallback` is `now` at the call site and the row is seconds old, so giving up
 * costs almost nothing.
 */
function timestamptzToEpochMs(v: unknown, fallback: number): number {
  if (typeof v !== "string") return fallback;
  const direct = Date.parse(v);
  if (Number.isFinite(direct)) return direct;
  const iso = v.trim().replace(" ", "T").replace(/([+-]\d{2})$/, "$1:00");
  const retry = Date.parse(iso);
  return Number.isFinite(retry) ? retry : fallback;
}

/** A `public.prices_live` row (raw, pre-coercion) as Realtime delivers it. */
export interface PriceRow {
  ticker?: unknown;
  /** Finnhub `c` — the quote. */
  price?: unknown;
  /** Finnhub `d` — absolute change. Carried by the table, unused by the UI. */
  change?: unknown;
  /** Finnhub `dp` — percent change, in POINTS. */
  change_pct?: unknown;
  /** Finnhub `t` widened to `timestamptz` by the publisher. */
  quoted_at?: unknown;
  updated_at?: unknown;
}

/** A Coinbase public `ticker` message (only the fields we read). */
export interface CoinbaseTicker {
  type?: string;
  product_id?: string;
  price?: string;
  open_24h?: string;
  time?: string;
}

/**
 * A `public.prices_live` row → a LIVE {@link LiveQuote}, or `null` when the row
 * is unusable. Live (non-stale) by definition: the row exists only because the
 * service-role publisher wrote a fresh Finnhub quote into it.
 *
 * `null` when the ticker is missing or the price is not a finite number. A
 * DELETE event falls into that first case for free — its `new` is `{}`, so it
 * carries no ticker and drops out here rather than needing an eventType check
 * at the call site.
 *
 * Note the bar is "finite", not "positive", matching {@link seedRowToLive}: a
 * non-positive mark is left to the consumers that already gate on it
 * (`positionRowToLive`, `computeLiveTotal`) rather than being swallowed here,
 * where dropping the row would silently pin the symbol to its stale seed.
 *
 * `change_pct` is Finnhub `dp`, already in percent POINTS. The `change` column
 * (Finnhub `d`) is intentionally dropped — {@link LiveQuote} has never carried
 * an absolute-change field and nothing in the UI asks for one.
 */
export function priceRowToLive(row: PriceRow, now: number = Date.now()): LiveQuote | null {
  const symbol = typeof row.ticker === "string" ? row.ticker.trim().toUpperCase() : "";
  const price = num(row.price);
  if (!symbol || price == null) return null;
  const changePct = num(row.change_pct) ?? 0;
  return {
    symbol,
    price,
    changePct,
    up: changePct >= 0,
    ts: timestamptzToEpochMs(row.quoted_at, now),
    stale: false,
    source: "postgres_changes",
  };
}

/**
 * Coinbase `ticker` message → {@link LiveQuote}, or `null` when it is not a
 * usable ticker (wrong type, missing product/price). `%chg` is computed from
 * `open_24h`; a missing/zero open yields `0` (never `Infinity`).
 */
export function coinbaseTickerToLive(
  msg: CoinbaseTicker,
  now: number = Date.now(),
): LiveQuote | null {
  if (msg?.type !== "ticker" || !msg.product_id) return null;
  const price = num(msg.price);
  if (price == null || price <= 0) return null;
  const open = num(msg.open_24h);
  const changePct = open != null && open > 0 ? ((price - open) / open) * 100 : 0;
  return {
    symbol: msg.product_id.toUpperCase(),
    price,
    changePct,
    up: changePct >= 0,
    ts: toEpochMs(msg.time ? Date.parse(msg.time) : now, now),
    stale: false,
    source: "coinbase",
  };
}

/**
 * A `public_price_latest` row → a STALE seed {@link LiveQuote}. `change_pct` is
 * the prior-session daily move (migration 052) so a seeded equity shows its real
 * last close instead of a flat 0% — a missing/absent change reads as 0. Kept
 * `stale` so it never counts as a live tick (a prices_live/Coinbase quote
 * always overwrites it, and the live book valuation ignores it).
 */
export function seedRowToLive(
  row: { ticker?: unknown; close?: unknown; change_pct?: unknown },
  now: number = Date.now(),
): LiveQuote | null {
  const symbol = typeof row.ticker === "string" ? row.ticker.trim().toUpperCase() : "";
  const price = num(row.close);
  if (!symbol || price == null) return null;
  const changePct = num(row.change_pct) ?? 0;
  return {
    symbol,
    price,
    changePct,
    up: changePct >= 0,
    ts: now,
    stale: true,
    source: "seed",
  };
}

/**
 * Merge incoming quotes into a map. Rule: a `seed` quote never overwrites an
 * existing LIVE (`!stale`) quote — seeds only fill gaps and never downgrade a
 * real tick. Live quotes always win. Returns a new map (or `prev` unchanged
 * when nothing applied, to keep referential stability for React).
 */
export function applyQuotes(prev: LivePriceMap, incoming: readonly LiveQuote[]): LivePriceMap {
  if (incoming.length === 0) return prev;
  let changed = false;
  const next: LivePriceMap = { ...prev };
  for (const q of incoming) {
    const existing = next[q.symbol];
    if (q.source === "seed" && existing && !existing.stale) continue;
    next[q.symbol] = q;
    changed = true;
  }
  return changed ? next : prev;
}

/** `public_portfolio_positions` row shape (raw, pre-coercion). */
export interface PositionRow {
  ticker?: unknown;
  name?: unknown;
  category?: unknown;
  sector_bucket?: unknown;
  weight_pct?: unknown;
  entry_price?: unknown;
  entry_date?: unknown;
  current_price?: unknown;
  day_change_pct?: unknown;
  unrealized_pnl_pct?: unknown;
  since_entry_return_pct?: unknown;
  metrics_as_of?: unknown;
}

const asStr = (v: unknown): string | null => (typeof v === "string" && v ? v : null);

/** Enrich a raw position row with its live mark. `isLive` is true ONLY for a non-stale quote. */
export function positionRowToLive(row: PositionRow, quotes: LivePriceMap): LivePosition {
  const ticker = typeof row.ticker === "string" ? row.ticker.trim().toUpperCase() : "";
  const currentPrice = num(row.current_price);
  const q = quotes[ticker];
  const isLive = Boolean(q && !q.stale && Number.isFinite(q.price) && q.price > 0);
  return {
    ticker,
    name: asStr(row.name),
    category: asStr(row.category),
    sectorBucket: asStr(row.sector_bucket),
    weightPct: num(row.weight_pct) ?? 0,
    entryPrice: num(row.entry_price),
    entryDate: asStr(row.entry_date),
    currentPrice,
    dayChangePct: num(row.day_change_pct),
    unrealizedPnlPct: num(row.unrealized_pnl_pct),
    sinceEntryReturnPct: num(row.since_entry_return_pct),
    metricsAsOf: asStr(row.metrics_as_of),
    livePrice: isLive ? q!.price : currentPrice,
    isLive,
  };
}

/** `public_accounting_nav_history` / `public_nav_history` row → {@link NavPoint} | null. */
export function navRowToPoint(row: {
  date?: unknown;
  nav?: unknown;
  cash_pct?: unknown;
  invested_pct?: unknown;
  day_return_pct?: unknown;
  source?: unknown;
  contract?: unknown;
}): NavPoint | null {
  const date = asStr(row.date);
  const nav = num(row.nav);
  if (!date || nav == null) return null;
  return {
    date,
    nav,
    cashPct: num(row.cash_pct),
    investedPct: num(row.invested_pct),
    dayReturnPct: num(row.day_return_pct),
    source: asStr(row.source),
    contract: asStr(row.contract),
  };
}

/**
 * Live book valuation. `liveVsMarkPct` = Σ weightᵢ·(livePriceᵢ/markᵢ − 1) over
 * positions with a REAL (non-stale) quote and a positive mark; every other leg
 * (stale seed, CASH, missing mark) contributes 0 → flat. With no live ticks the
 * sum is 0 and `liveTotalValue` equals `latestNav` (the published book value).
 */
export function computeLiveTotal(
  positions: readonly LivePosition[],
  quotes: LivePriceMap,
  latestNav: number | null,
): { liveVsMarkPct: number; liveTotalValue: number | null } {
  let move = 0;
  for (const p of positions) {
    const mark = p.currentPrice;
    if (mark == null || mark <= 0) continue;
    const q = quotes[p.ticker];
    if (!q || q.stale || !Number.isFinite(q.price) || q.price <= 0) continue;
    move += (p.weightPct / 100) * (q.price / mark - 1);
  }
  return {
    liveVsMarkPct: move * 100,
    liveTotalValue: latestNav == null ? null : latestNav * (1 + move),
  };
}
