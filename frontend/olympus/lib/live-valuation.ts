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
 *
 * PROVENANCE AND FRESHNESS ARE TWO DIFFERENT CLAIMS, and conflating them reproduces the very
 * ambiguity above. `source: 'live'` says only WHERE the mark came from: a `prices_live` row
 * supplied it. It does NOT say the mark is current, because rows in that table persist
 * indefinitely — the publisher only upserts (migration 063 defines no DELETE path) and is
 * idle outside 13:00–01:00 UTC Mon–Fri — so a row is present all night, all weekend, and
 * right through a per-ticker feed freeze. Measured in production on 2026-08-04: 20 rows whose
 * `quoted_at` ranged from 13.8 to 18.6 hours old, and, within one session, two tickers five
 * hours apart. Hence {@link Valuation.isFresh}, the separate age test against
 * {@link LIVE_QUOTE_FRESH_MS}: `source` licenses the ATTRIBUTION, `isFresh` licenses the WORD
 * "live". The value never changes — only the label.
 *
 * The reference instant is a PARAMETER ({@link valuePosition}'s `nowMs`), never a clock read
 * in here. This module has no default for it: freshness has to be deterministic under test,
 * and the only place allowed to reach for a real clock is the component boundary.
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

/**
 * Which layer produced a {@link Valuation} — PROVENANCE, not recency. `unavailable` renders
 * nothing — never a 0. Whether a `live` mark may be CALLED live is {@link Valuation.isFresh}.
 */
export type ValuationSource = 'live' | 'close' | 'unavailable';

export interface Valuation {
  source: ValuationSource;
  /** The mark the figures were computed from; null when `source` is `unavailable`. */
  price: number | null;
  /** Since-entry unrealized return in percent POINTS (1.24 = +1.24%). */
  unrealizedPct: number | null;
  /** `quoted_at` for `live`, `metrics_as_of` for `close`, null when unavailable. */
  asOf: string | null;
  /**
   * Whether `asOf` is recent enough for the figure to be presented as CURRENT — the freshness
   * claim `source` deliberately does not make (see the header). True only for a `live` mark
   * whose `quoted_at` is within {@link LIVE_QUOTE_FRESH_MS} of the caller's `nowMs`.
   *
   * FALSE on every `close` and `unavailable` result, so a UI branch must gate on
   * `source === 'live' && isFresh`. Branching on `!isFresh` ALONE mislabels a perfectly
   * ordinary close as a stale quote — the mistake RiskEnvelopeCell's `basis` line invites.
   */
  isFresh: boolean;
  /**
   * Age of `asOf` at the caller's `nowMs`, in milliseconds; null when it cannot be computed.
   * Populated for a `close` too (the field means "age of `asOf`", uniformly), but nothing
   * renders it there: a close is dated by its DAY, and a clock-derived age on the close branch
   * would differ between the static prerender and hydration.
   */
  ageMs: number | null;
}

/**
 * How recent `quoted_at` must be for a live mark to be called CURRENT, in milliseconds.
 *
 * Taken from the publisher's real cadence, not picked for roundness: pg_cron invokes the
 * `prices-live` edge function ONCE EVERY 60s during extended US market hours, behind a
 * 50-second refresh lease (migration 064, lines 9-11 and 136-139). So a covered ticker's
 * `quoted_at` advances about once a minute while the feed is ticking, and five minutes is FIVE
 * CONSECUTIVE MISSED CYCLES — well past cron jitter, an edge-function cold start, or a single
 * retry, and therefore unambiguous evidence that the feed is not currently ticking FOR THAT
 * TICKER. A tighter bound (one or two cycles) would flap on ordinary jitter.
 *
 * Erring tight is deliberate and cheap. `quoted_at` is the EXCHANGE tick time, so a thinly
 * traded symbol can genuinely sit still for minutes with the market wide open, and this
 * threshold then declines to call it live. That is the honest outcome, because the figure is
 * still rendered either way — it remains the best mark available — and only the CLAIM changes,
 * from the word "live" to the instant it was actually quoted at. The failure being prevented
 * is the asymmetric one: a number labelled "live" whose quote last moved 18 hours ago.
 */
export const LIVE_QUOTE_FRESH_MS = 5 * 60 * 1000;

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

/**
 * Age of an `asOf` stamp at `nowMs`, in milliseconds — null when there is nothing comparable
 * (absent, or a value {@link normalizeTimestamptz} had to pass through verbatim).
 *
 * A NEGATIVE age is clamped to 0 rather than reported. `quoted_at` is stamped by the exchange
 * and `nowMs` is read from the reader's machine, so a quote a few seconds "in the future" is
 * ordinary clock skew, not a stale quote — it must count as fresh and must never render as
 * "-3s old".
 */
export function quoteAgeMs(asOf: string | null | undefined, nowMs: number): number | null {
  if (!asOf || !Number.isFinite(nowMs)) return null;
  const ts = Date.parse(asOf);
  if (!Number.isFinite(ts)) return null;
  return Math.max(0, nowMs - ts);
}

/**
 * Is a quote of this age recent enough to be CALLED live?
 *
 * Inclusive at the bound (`<=`): a quote exactly {@link LIVE_QUOTE_FRESH_MS} old is fresh, one
 * millisecond older is not. A boundary has to fall on one side, and the threshold is already
 * five times the publisher's period, so the inclusive side is the one that does not clip a
 * quote that landed exactly on the last legitimate cycle.
 *
 * An UNKNOWN age (null — missing or unparseable stamp) is NOT fresh. Same direction
 * lib/snapshot-staleness.ts fails: an unattributable figure must never be claimed as current.
 */
export function isQuoteFresh(ageMs: number | null, thresholdMs = LIVE_QUOTE_FRESH_MS): boolean {
  return ageMs != null && ageMs <= thresholdMs;
}

/**
 * A compact age for the not-current label — `45s`, `12m`, `3h`, `2d`. Null when unknown, and
 * the caller then says so rather than printing a fabricated number.
 *
 * Deliberately COARSE: the exact instant is rendered beside it (see the table's
 * `attributionDetail`), and a seconds-precision string would imply the figure is updating that
 * often, which — for a quote this function is only asked about because it stopped advancing —
 * is exactly the wrong impression.
 */
export function formatQuoteAge(ageMs: number | null): string | null {
  if (ageMs == null || !Number.isFinite(ageMs)) return null;
  const seconds = Math.max(0, Math.floor(ageMs / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

/** Nothing to show. A fresh object each call, so no caller can alias a shared result. */
function unavailable(): Valuation {
  return {
    source: 'unavailable',
    price: null,
    unrealizedPct: null,
    asOf: null,
    isFresh: false,
    ageMs: null,
  };
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
 *
 * `nowMs` is REQUIRED, and no clock is read in this module — see the header. It only ever
 * affects {@link Valuation.isFresh} and {@link Valuation.ageMs}, i.e. the LABEL; the fallback
 * order above, the chosen mark and `unrealizedPct` are identical whatever instant is passed. A
 * quote that has gone stale is still the best mark available, so it is still the one returned.
 */
export function valuePosition(
  position: ValuablePosition,
  quote: LiveQuote | null | undefined,
  nowMs: number
): Valuation {
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
    const asOf = quote?.quotedAt || null;
    // PER TICKER, from this row's own `quoted_at` — never from a global "is the market open?"
    // test, which is precisely what misses the case that was measured: one ticker frozen at
    // 15:08 UTC while its neighbours advanced to 20:00, all mid-session.
    const ageMs = quoteAgeMs(asOf, nowMs);
    return {
      source: 'live',
      price: livePrice,
      unrealizedPct: ((livePrice - entry) / entry) * 100,
      asOf,
      isFresh: isQuoteFresh(ageMs),
      ageMs,
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
      // A close is NEVER fresh — that is what makes it a close, and it is labelled as one. The
      // age is filled in for uniformity but is not rendered on this branch (see `ageMs`).
      isFresh: false,
      ageMs: quoteAgeMs(closeAsOf, nowMs),
    };
  }

  // 3 — neither lane has anything defensible.
  return unavailable();
}
