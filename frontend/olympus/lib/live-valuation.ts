/**
 * Live valuation overlay (#1833) — the DISPLAY layer, and the wall between it and the record.
 *
 * TWO LAYERS THAT MUST NOT MERGE:
 *
 *   1. THE RECORD — close-to-close, persisted, untouched by this module.
 *      `refresh_performance_metrics.py` writes `positions.current_price`,
 *      `unrealized_pnl_pct`, `day_change_pct`, `since_entry_return_pct` and `metrics_as_of`
 *      once nightly from the official close. It is the ONLY input to performance metrics,
 *      NAV history, returns, Sharpe, drawdown and attribution, and it must stay
 *      reproducible: same inputs, same numbers, whenever computed.
 *
 *   2. THE DISPLAY — this file. Unrealized performance at the current moment, derived in the
 *      browser from `public.prices_live` and PERSISTED NOWHERE.
 *
 * THE INVARIANT: a live price must NEVER reach the close-keyed record. That is a live risk
 * because `positions.current_price` currently does both jobs — it is the nightly close AND
 * the field the UI renders — so the tempting shortcut is to write `prices_live` into it. Then
 * the performance batch would read a mid-session price as the day's close, `nav_history`
 * would depend on WHEN the pipeline ran, and the same day's return would differ between
 * computations. Invisible, plausible, and it destroys reproducibility (same class as #1745
 * and #1761). Hence: everything here is PURE and READ-ONLY. No I/O, no React, no writes.
 * {@link valuePosition} never mutates its argument — it returns a fresh {@link Valuation}.
 *
 * ATTRIBUTION IS PART OF THE FEATURE. A live figure and a close figure that render
 * identically are the ambiguity #1750 flags for frozen documents: the reader cannot tell
 * current from stale. So every result carries the `source` that produced it and the `asOf`
 * that source stamps — `quoted_at` for live, `metrics_as_of` for a close — and callers are
 * expected to label them differently.
 */

/** A usable quote from `public.prices_live`, keyed by ticker in {@link LiveQuoteMap}. */
export interface LiveQuote {
  /** Last trade price (`prices_live.price`, Finnhub `c`). Finite; may be 0 when halted. */
  price: number;
  /**
   * Change vs the PRIOR CLOSE in percent points (`change_pct`, Finnhub `dp`): 1.24 means
   * +1.24%. NOT the same number as {@link Valuation.unrealizedPct}, which is measured
   * against `entry_price` — a day move and a since-entry move must never be rendered
   * interchangeably.
   */
  changePct: number | null;
  /**
   * The EXCHANGE tick time (`quoted_at`), canonicalized to ISO-8601. Never `updated_at`:
   * that is our write clock and advances even when the market is quiet.
   */
  quotedAt: string;
}

/** Live quotes keyed by UPPERCASE ticker. Absent key = no live coverage for that symbol. */
export type LiveQuoteMap = Readonly<Record<string, LiveQuote>>;

/** Which layer produced a {@link Valuation}. `unavailable` renders nothing — never a 0. */
export type ValuationSource = 'live' | 'close' | 'unavailable';

export interface Valuation {
  source: ValuationSource;
  /** The mark the figures were computed from; null when `source` is `unavailable`. */
  price: number | null;
  /** Since-entry unrealized return in percent POINTS (1.24 = +1.24%). */
  unrealizedPct: number | null;
  /** `quoted_at` for `live`, `metrics_as_of` for `close`, null when unavailable. */
  asOf: string | null;
}

/**
 * The fields {@link valuePosition} reads. A structural subset satisfied by both the
 * assembled `Position` (lib/types.ts) and a raw `TableRow<'positions'>`, so callers pass
 * whichever they hold without a conversion step.
 */
export interface ValuablePosition {
  ticker: string;
  entry_price: number | null;
  /** The nightly CLOSE. Read here, never written — see the header.  */
  current_price?: number | null;
  /** The persisted since-entry return (the record's own number). */
  unrealized_pnl_pct?: number | null;
  /** When the close-keyed metrics above were computed. */
  metrics_as_of?: string | null;
}

/**
 * A `prices_live` row as delivered by PostgREST (seed) or Realtime (WAL), pre-coercion.
 * Documentation of the wire shape, NOT an annotation for callers to reach for: every field
 * is `unknown`, so typing a variable with it buys no checking. Hand raw rows to
 * {@link liveQuoteFromRow} as `unknown` and let it do the validating.
 */
interface RawPriceRow {
  ticker?: unknown;
  price?: unknown;
  change_pct?: unknown;
  quoted_at?: unknown;
}

/** One parsed row: the map key and its value, kept separate so the key stays explicit. */
export interface ParsedQuoteRow {
  /** Uppercased here, not trusted from the row — see {@link liveQuoteFromRow}. */
  ticker: string;
  quote: LiveQuote;
}

/** Coerce a PostgREST numeric (number OR decimal-string) → a finite number, else null. */
function finiteNum(value: unknown): number | null {
  if (value == null || value === '') return null;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** CASH is the invested/cash split, not an instrument — same test as book-reconciliation.ts. */
function isCashTicker(ticker: string): boolean {
  return ticker.trim().toUpperCase() === 'CASH';
}

/**
 * A Postgres `timestamptz` → a canonical ISO-8601 string, or the raw value when it cannot
 * be parsed at all (null only when there is nothing usable).
 *
 * Load-bearing, because the SAME column arrives in TWO formats depending on the lane.
 * PostgREST renders the seed as `2026-08-03T14:23:00+00:00`; Realtime renders it off the
 * WAL as `2026-08-03 14:23:00+00` — space separator, two-digit offset — and neither that
 * separator nor a bare two-digit offset is in the ECMA-262 `Date.parse` grammar, so engines
 * disagree about it. Without this, `new Date(quotedAt)` works on the seed and silently
 * yields `Invalid Date` from the first realtime tick onward. Canonicalizing BOTH to
 * `toISOString()` also means one instant has one string, so a re-render caused only by a
 * format change is impossible.
 */
export function normalizeTimestamptz(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const raw = value.trim();
  if (!raw) return null;
  const direct = Date.parse(raw);
  if (Number.isFinite(direct)) return new Date(direct).toISOString();
  const iso = raw.replace(' ', 'T').replace(/([+-]\d{2})$/, '$1:00');
  const retry = Date.parse(iso);
  return Number.isFinite(retry) ? new Date(retry).toISOString() : raw;
}

/**
 * A `prices_live` row → {@link ParsedQuoteRow}, or null when the row is unusable.
 *
 * Pure so the rejection rules are testable instead of buried in a subscription effect.
 * Rejects when:
 *   - there is no ticker. A Realtime DELETE payload's `new` is `{}`, so it lands here for
 *     free rather than needing an eventType check at the call site — and a partial row must
 *     never be written into the map.
 *   - `price` is not finite. Note the bar is finite, not positive: migration 063 declined a
 *     `price > 0` CHECK because Finnhub legitimately returns 0 for a halted or unrecognised
 *     symbol and says "consumers gate on the value". The map therefore reports the table
 *     honestly and {@link valuePosition} is where a 0 mark is refused as a valuation.
 *   - `quoted_at` is missing. The column is NOT NULL, so its absence means a malformed
 *     payload; and an unattributed live figure is indistinguishable from a close, which is
 *     precisely what this feature must not produce.
 *
 * The ticker is uppercased ON READ rather than assumed: migration 063 deliberately declined
 * a ticker-casing CHECK (to keep one bad symbol from failing the whole minute's upsert), so
 * the publisher's casing is a convention, not a guarantee.
 */
export function liveQuoteFromRow(row: unknown): ParsedQuoteRow | null {
  if (!row || typeof row !== 'object') return null;
  const r = row as RawPriceRow;
  const ticker = typeof r.ticker === 'string' ? r.ticker.trim().toUpperCase() : '';
  const price = finiteNum(r.price);
  const quotedAt = normalizeTimestamptz(r.quoted_at);
  if (!ticker || price == null || !quotedAt) return null;
  return { ticker, quote: { price, changePct: finiteNum(r.change_pct), quotedAt } };
}

/**
 * Fold parsed quotes into a {@link LiveQuoteMap}, keeping the NEWER `quoted_at` per ticker.
 *
 * The seed is an HTTP read of the same table the subscription streams, so the two lanes race:
 * a realtime tick can land while the seed query is still in flight, and a naive
 * `{ ...prev, ...incoming }` would let the seed's older row overwrite the fresher tick,
 * leaving the overlay a minute behind with nothing to indicate it.
 * (frontend/digiquant-web solves the same race with a seed/live flag; both lanes here read
 * one table, so `quoted_at` orders them on the exchange clock instead.)
 *
 * Precisely what this does and does not promise: an existing entry is kept ONLY when its
 * `quoted_at` is strictly newer. Incoming wins on a tie and whenever the comparison is not
 * decidable (an unparseable stamp), i.e. it degrades to last-write-wins rather than pinning a
 * stale value. A tie is the common case in a quiet minute — both lanes then carry the same
 * row, so the overwrite is a no-op in value terms.
 *
 * Returns `prev` UNCHANGED — same reference — when nothing was taken, so a no-op batch cannot
 * trigger a re-render.
 */
export function mergeQuotes(
  prev: LiveQuoteMap,
  incoming: Readonly<Record<string, LiveQuote>>
): LiveQuoteMap {
  const keys = Object.keys(incoming);
  if (keys.length === 0) return prev;
  const next: Record<string, LiveQuote> = { ...prev };
  let changed = false;
  for (const key of keys) {
    const quote = incoming[key];
    if (!quote) continue;
    const existing = next[key];
    if (existing) {
      if (existing === quote) continue;
      const held = Date.parse(existing.quotedAt);
      const arriving = Date.parse(quote.quotedAt);
      if (Number.isFinite(held) && Number.isFinite(arriving) && held > arriving) continue;
    }
    next[key] = quote;
    changed = true;
  }
  return changed ? next : prev;
}

/** Nothing to show. A fresh object each call, so no caller can alias a shared result. */
function unavailable(): Valuation {
  return { source: 'unavailable', price: null, unrealizedPct: null, asOf: null };
}

/**
 * Value one position at the current moment, in percent POINTS, with its provenance.
 *
 * Fallback order — mandatory, and never a midpoint and never a zero:
 *   1. `live`  — a `prices_live` quote exists → its price, `asOf` = `quoted_at`.
 *   2. `close` — no live quote, but `current_price` + `metrics_as_of` exist → the close,
 *      `asOf` = `metrics_as_of`, labelled as a close so the reader can tell it is stale.
 *   3. `unavailable` — neither. Callers render nothing/an em-dash. NEVER 0, and never the
 *      midpoint of a range: a fabricated centre reads as a real measurement.
 *
 * A missing cost basis makes the whole valuation `unavailable`, ahead of either price
 * branch. The unit of meaning here is unrealized performance versus entry, so a mark with
 * no basis is not a partial valuation — and it is the guard that keeps a null or
 * non-positive `entry_price` from producing `Infinity`/`NaN` instead of a blank.
 */
export function valuePosition(position: ValuablePosition, quote?: LiveQuote | null): Valuation {
  // Belt and braces: a CASH sleeve is a NAV split line, not an instrument. It has no basis
  // so the guard below would already catch it, but any price on it would be spurious and
  // 0% would read as "flat" rather than "not applicable".
  if (isCashTicker(position.ticker)) return unavailable();

  const entry = finiteNum(position.entry_price);
  if (entry == null || entry <= 0) return unavailable();

  // 1 — live. A non-positive mark (halted symbol, per migration 063) is not a valuation, so
  // it falls through to the close rather than rendering the position down ~100%.
  const livePrice = quote ? finiteNum(quote.price) : null;
  if (livePrice != null && livePrice > 0) {
    return {
      source: 'live',
      price: livePrice,
      unrealizedPct: ((livePrice - entry) / entry) * 100,
      asOf: quote?.quotedAt || null,
    };
  }

  // 2 — close. Prefer the STORED `unrealized_pnl_pct` over recomputing it: that column is
  // the record, written by the nightly batch, and recomputing from `current_price` risks
  // disagreeing with the persisted series over rounding or over an entry basis the batch
  // resolved differently. Recompute only when the record has no number.
  const closePrice = finiteNum(position.current_price);
  const closeAsOf = position.metrics_as_of ?? null;
  if (closePrice != null && closePrice > 0 && closeAsOf) {
    const stored = finiteNum(position.unrealized_pnl_pct);
    return {
      source: 'close',
      price: closePrice,
      unrealizedPct: stored ?? ((closePrice - entry) / entry) * 100,
      asOf: closeAsOf,
    };
  }

  // 3 — neither lane has anything defensible.
  return unavailable();
}
