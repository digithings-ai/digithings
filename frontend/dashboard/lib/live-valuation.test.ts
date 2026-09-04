import { describe, expect, it } from 'vitest';
import {
  formatQuoteAge,
  isQuoteFresh,
  liveQuoteFromRow,
  LIVE_QUOTE_FRESH_MS,
  mergeQuotes,
  normalizeTimestamptz,
  quoteAgeMs,
  valuePosition,
  type LiveQuote,
  type LiveQuoteMap,
  type ValuablePosition,
} from './live-valuation';

const QUOTED_AT = '2026-08-03T18:23:00.000Z';
const METRICS_AS_OF = '2026-07-31T20:00:00.000Z';

/**
 * The reference instant every test passes explicitly — one minute after {@link QUOTED_AT}, so
 * the quote is comfortably fresh. `valuePosition` reads no clock, so nothing in this file
 * depends on when it runs: the freshness assertions below move `nowMs`, never the system time.
 */
const NOW = Date.parse(QUOTED_AT) + 60_000;

/** A held row with both layers populated: nightly close metrics AND a valid basis. */
const position = (over: Partial<ValuablePosition> = {}): ValuablePosition => ({
  ticker: 'XLE',
  entry_price: 100,
  current_price: 110,
  unrealized_pnl_pct: 10,
  metrics_as_of: METRICS_AS_OF,
  ...over,
});

const quote = (over: Partial<LiveQuote> = {}): LiveQuote => ({
  price: 120,
  changePct: 1.24,
  quotedAt: QUOTED_AT,
  ...over,
});

describe('valuePosition — fallback order (#1833)', () => {
  it('live wins over close: the live price and quoted_at, not the stored close', () => {
    const v = valuePosition(position(), quote(), NOW);
    expect(v.source).toBe('live');
    expect(v.price).toBe(120);
    expect(v.asOf).toBe(QUOTED_AT);
    // Computed against entry (100 → 120), NOT the stored 10 that belongs to the close.
    expect(v.unrealizedPct).toBeCloseTo(20, 10);
  });

  it('close is used when there is no live row, labelled as a close', () => {
    const v = valuePosition(position(), undefined, NOW);
    expect(v.source).toBe('close');
    expect(v.price).toBe(110);
    expect(v.asOf).toBe(METRICS_AS_OF);
  });

  it('close prefers the STORED unrealized_pnl_pct over recomputing (it is the record)', () => {
    // Recomputing 100 → 110 would give 10.0; the record says 9.87 (the batch resolved its
    // own basis). The persisted series wins so the overlay cannot disagree with it.
    const v = valuePosition(position({ unrealized_pnl_pct: 9.87 }), null, NOW);
    expect(v.source).toBe('close');
    expect(v.unrealizedPct).toBe(9.87);
  });

  it('close recomputes only when the record carries no percentage', () => {
    const v = valuePosition(position({ unrealized_pnl_pct: null }), null, NOW);
    expect(v.source).toBe('close');
    expect(v.unrealizedPct).toBeCloseTo(10, 10);
  });

  it('unavailable when neither lane has anything — never 0, never a midpoint', () => {
    const v = valuePosition(position({ current_price: null, metrics_as_of: null }), undefined, NOW);
    expect(v).toEqual({
      source: 'unavailable',
      price: null,
      unrealizedPct: null,
      asOf: null,
      isFresh: false,
      ageMs: null,
    });
  });

  it('unavailable when the close has a price but no metrics_as_of (an unattributed close)', () => {
    const v = valuePosition(position({ metrics_as_of: null }), undefined, NOW);
    expect(v.source).toBe('unavailable');
  });

  it('a non-positive live mark (halted symbol) falls through to the close, not to −100%', () => {
    // Migration 063 declined a `price > 0` CHECK because Finnhub returns 0 for a halted or
    // unrecognised symbol and leaves consumers to gate on the value.
    const v = valuePosition(position(), quote({ price: 0 }), NOW);
    expect(v.source).toBe('close');
    expect(v.unrealizedPct).toBe(10);
  });
});

describe('valuePosition — entry basis guard (no Infinity, no NaN)', () => {
  for (const entry of [null, 0, -12.5] as const) {
    it(`unavailable when entry_price is ${String(entry)}`, () => {
      const withLive = valuePosition(position({ entry_price: entry }), quote(), NOW);
      const withCloseOnly = valuePosition(position({ entry_price: entry }), undefined, NOW);
      expect(withLive.source).toBe('unavailable');
      expect(withLive.unrealizedPct).toBeNull();
      expect(withCloseOnly.source).toBe('unavailable');
      // The failure mode this guard exists for: /0 → Infinity, null → NaN.
      expect(Number.isFinite(withLive.unrealizedPct as number)).toBe(false);
    });
  }

  it('a CASH sleeve lands on unavailable, not 0% — it has no basis and no meaningful price', () => {
    const cash: ValuablePosition = {
      ticker: 'CASH',
      entry_price: null,
      current_price: null,
      unrealized_pnl_pct: null,
      metrics_as_of: METRICS_AS_OF,
    };
    expect(valuePosition(cash, undefined, NOW).source).toBe('unavailable');
    // Explicit even if the sleeve were ever handed a price and a basis: it is a NAV split
    // line, not an instrument.
    expect(valuePosition({ ...cash, entry_price: 1, current_price: 1 }, quote(), NOW).source).toBe(
      'unavailable'
    );
    expect(valuePosition({ ...cash, ticker: ' cash ' }, undefined, NOW).source).toBe('unavailable');
  });
});

describe('valuePosition — scale and immutability', () => {
  it('unrealizedPct is in PERCENT POINTS: 1.24, not 0.0124 (matches change_pct)', () => {
    const v = valuePosition(position({ entry_price: 100 }), quote({ price: 101.24 }), NOW);
    expect(v.unrealizedPct).toBeCloseTo(1.24, 10);
    expect(v.unrealizedPct).not.toBeCloseTo(0.0124, 6);
  });

  it('a negative move is a negative percentage, not an absolute one', () => {
    const v = valuePosition(position({ entry_price: 200 }), quote({ price: 150 }), NOW);
    expect(v.unrealizedPct).toBeCloseTo(-25, 10);
  });

  it('a live quote NEVER changes any stored field — the record is read, not written', () => {
    // The invariant: `positions.current_price`/`unrealized_pnl_pct`/`metrics_as_of` are the
    // nightly CLOSE the performance batch reads. A live price reaching them would make
    // nav_history depend on WHEN the pipeline ran.
    const p = position();
    const before = { ...p };
    const q = quote();
    const qBefore = { ...q };
    const v = valuePosition(p, q, NOW);

    expect(p).toEqual(before);
    expect(p.current_price).toBe(110);
    expect(p.unrealized_pnl_pct).toBe(10);
    expect(p.metrics_as_of).toBe(METRICS_AS_OF);
    expect(q).toEqual(qBefore);
    // The result is a fresh object, not an aliased view of either input.
    expect(v).not.toBe(p);
    expect(Object.is(v, q)).toBe(false);
  });

  it('two unavailable results are distinct objects (no shared mutable sentinel)', () => {
    const a = valuePosition(position({ entry_price: null }), undefined, NOW);
    const b = valuePosition(position({ entry_price: null }), undefined, NOW);
    expect(a).toEqual(b);
    expect(a).not.toBe(b);
  });
});

describe('liveQuoteFromRow — the read boundary', () => {
  it('parses a PostgREST seed row and uppercases the ticker on read', () => {
    // 063 declined a ticker-casing CHECK, so the publisher's casing is a convention only.
    const parsed = liveQuoteFromRow({
      ticker: 'xle',
      price: 120.5,
      change_pct: 1.24,
      quoted_at: '2026-08-03T18:23:00+00:00',
    });
    expect(parsed?.ticker).toBe('XLE');
    expect(parsed?.quote.price).toBe(120.5);
    expect(parsed?.quote.changePct).toBe(1.24);
    expect(parsed?.quote.quotedAt).toBe(QUOTED_AT);
  });

  it('coerces PostgREST decimal-strings to numbers', () => {
    const parsed = liveQuoteFromRow({
      ticker: 'XLE',
      price: '120.5',
      change_pct: '-0.75',
      quoted_at: QUOTED_AT,
    });
    expect(parsed?.quote.price).toBe(120.5);
    expect(parsed?.quote.changePct).toBe(-0.75);
  });

  it('keeps a 0 price (halted symbol) — gating on it is valuePosition’s job', () => {
    expect(liveQuoteFromRow({ ticker: 'XLE', price: 0, quoted_at: QUOTED_AT })?.quote.price).toBe(0);
  });

  it('null change_pct survives as null (never coerced to 0)', () => {
    const parsed = liveQuoteFromRow({ ticker: 'XLE', price: 10, change_pct: null, quoted_at: QUOTED_AT });
    expect(parsed?.quote.changePct).toBeNull();
  });

  it('rejects a DELETE payload (empty `new`) rather than writing a partial row', () => {
    expect(liveQuoteFromRow({})).toBeNull();
    expect(liveQuoteFromRow(undefined)).toBeNull();
    expect(liveQuoteFromRow(null)).toBeNull();
  });

  it('rejects rows with no usable price or no quoted_at', () => {
    expect(liveQuoteFromRow({ ticker: 'XLE', quoted_at: QUOTED_AT })).toBeNull();
    expect(liveQuoteFromRow({ ticker: 'XLE', price: 'n/a', quoted_at: QUOTED_AT })).toBeNull();
    expect(liveQuoteFromRow({ ticker: 'XLE', price: 10 })).toBeNull();
    expect(liveQuoteFromRow({ ticker: '   ', price: 10, quoted_at: QUOTED_AT })).toBeNull();
  });
});

describe('mergeQuotes — the seed must not clobber a fresher tick', () => {
  const at = (iso: string, price: number): LiveQuote => ({ price, changePct: null, quotedAt: iso });

  it('keeps the newer quoted_at when a late seed carries an older row', () => {
    const prev: LiveQuoteMap = { XLE: at('2026-08-03T18:23:00.000Z', 120) };
    const merged = mergeQuotes(prev, { XLE: at('2026-08-03T18:22:00.000Z', 119) });
    expect(merged.XLE?.price).toBe(120);
    // Nothing changed, so the same reference comes back — no re-render for a no-op batch.
    expect(merged).toBe(prev);
  });

  it('takes the incoming quote when it is newer, and leaves other tickers alone', () => {
    const prev: LiveQuoteMap = {
      XLE: at('2026-08-03T18:23:00.000Z', 120),
      TLT: at('2026-08-03T18:23:00.000Z', 90),
    };
    const merged = mergeQuotes(prev, { XLE: at('2026-08-03T18:24:00.000Z', 121) });
    expect(merged.XLE?.price).toBe(121);
    expect(merged.TLT?.price).toBe(90);
    expect(merged).not.toBe(prev);
    expect(prev.XLE?.price).toBe(120); // input map untouched
  });

  it('adds unseen tickers and returns prev unchanged for an empty batch', () => {
    const prev: LiveQuoteMap = {};
    expect(mergeQuotes(prev, {})).toBe(prev);
    expect(mergeQuotes(prev, { XLE: at('2026-08-03T18:23:00.000Z', 120) }).XLE?.price).toBe(120);
  });

  it('falls back to last-write-wins when a timestamp is not comparable', () => {
    const prev: LiveQuoteMap = { XLE: at('not a timestamp', 120) };
    expect(mergeQuotes(prev, { XLE: at('2026-08-03T18:23:00.000Z', 121) }).XLE?.price).toBe(121);
  });
});

describe('normalizeTimestamptz — both lanes render quoted_at differently', () => {
  it('PostgREST ISO and WAL-rendered timestamptz collapse to the same instant', () => {
    // Realtime delivers `2026-08-03 18:23:00+00` off the WAL — space separator and a bare
    // two-digit offset, neither of which is in the `Date.parse` grammar.
    const wal = normalizeTimestamptz('2026-08-03 18:23:00+00');
    const postgrest = normalizeTimestamptz('2026-08-03T18:23:00+00:00');
    expect(wal).toBe(QUOTED_AT);
    expect(postgrest).toBe(QUOTED_AT);
    expect(Number.isNaN(Date.parse(wal as string))).toBe(false);
  });

  it('returns null for non-strings and blanks, and keeps an unparseable value verbatim', () => {
    expect(normalizeTimestamptz(undefined)).toBeNull();
    expect(normalizeTimestamptz(1_767_000_000)).toBeNull();
    expect(normalizeTimestamptz('   ')).toBeNull();
    expect(normalizeTimestamptz('not a timestamp')).toBe('not a timestamp');
  });
});

describe('freshness primitives — quoted_at is the only recency source (#1833/#1834)', () => {
  it('pins the threshold to the publisher cadence: five 60s cycles', () => {
    // pg_cron drives `prices-live` once every 60s behind a 50s lease (migration 064). If that
    // cadence ever changes, this assertion is the reminder that the threshold derives from it.
    expect(LIVE_QUOTE_FRESH_MS).toBe(5 * 60 * 1000);
  });

  it('quoteAgeMs measures against the SUPPLIED instant, never a real clock', () => {
    expect(quoteAgeMs(QUOTED_AT, Date.parse(QUOTED_AT) + 90_000)).toBe(90_000);
    // The same stamp with a different reference instant gives a different age — proof the
    // function has no hidden clock of its own.
    expect(quoteAgeMs(QUOTED_AT, Date.parse(QUOTED_AT) + 7_200_000)).toBe(7_200_000);
  });

  it('quoteAgeMs clamps a future stamp to 0 (exchange clock vs browser clock skew)', () => {
    expect(quoteAgeMs(QUOTED_AT, Date.parse(QUOTED_AT) - 3_000)).toBe(0);
  });

  it('quoteAgeMs returns null when there is nothing comparable', () => {
    expect(quoteAgeMs(null, NOW)).toBeNull();
    expect(quoteAgeMs(undefined, NOW)).toBeNull();
    expect(quoteAgeMs('', NOW)).toBeNull();
    expect(quoteAgeMs('not a timestamp', NOW)).toBeNull();
    expect(quoteAgeMs(QUOTED_AT, Number.NaN)).toBeNull();
  });

  it('isQuoteFresh is inclusive AT the threshold and stale one millisecond past it', () => {
    expect(isQuoteFresh(LIVE_QUOTE_FRESH_MS)).toBe(true);
    expect(isQuoteFresh(LIVE_QUOTE_FRESH_MS + 1)).toBe(false);
    expect(isQuoteFresh(0)).toBe(true);
  });

  it('isQuoteFresh treats an UNKNOWN age as not fresh (fail loud)', () => {
    expect(isQuoteFresh(null)).toBe(false);
  });

  it('formatQuoteAge is coarse and never negative', () => {
    expect(formatQuoteAge(0)).toBe('0s');
    expect(formatQuoteAge(45_000)).toBe('45s');
    expect(formatQuoteAge(12 * 60_000)).toBe('12m');
    expect(formatQuoteAge(3 * 3_600_000)).toBe('3h');
    expect(formatQuoteAge(18.63 * 3_600_000)).toBe('18h'); // the age measured in production
    expect(formatQuoteAge(3 * 86_400_000)).toBe('3d');
    expect(formatQuoteAge(null)).toBeNull();
  });
});

describe('valuePosition — provenance and freshness are separate claims', () => {
  const AGE = (ms: number) => Date.parse(QUOTED_AT) + ms;

  it('a quote inside the window is live AND fresh, with its age', () => {
    const v = valuePosition(position(), quote(), AGE(60_000));
    expect(v.source).toBe('live');
    expect(v.isFresh).toBe(true);
    expect(v.ageMs).toBe(60_000);
  });

  it('an 18-hour-old quote keeps source live (provenance) but is NOT fresh', () => {
    // The production reading on 2026-08-04: rows present, `quoted_at` 18.6h old, and the table
    // rendering them as "live". `source` still says where the mark came from — that is a fact —
    // and `isFresh` is what withholds the word.
    const stale = valuePosition(position(), quote(), AGE(18.63 * 3_600_000));
    expect(stale.source).toBe('live');
    expect(stale.isFresh).toBe(false);
    expect(formatQuoteAge(stale.ageMs)).toBe('18h');
  });

  it('the VALUE is identical fresh or stale — only the label moves', () => {
    const fresh = valuePosition(position(), quote(), AGE(1_000));
    const stale = valuePosition(position(), quote(), AGE(9 * 3_600_000));
    expect(stale.price).toBe(fresh.price);
    expect(stale.unrealizedPct).toBe(fresh.unrealizedPct);
    expect(stale.asOf).toBe(fresh.asOf);
    expect(stale.source).toBe(fresh.source);
    expect(stale.isFresh).not.toBe(fresh.isFresh);
  });

  it('is fresh EXACTLY at the threshold and stale one millisecond later', () => {
    expect(valuePosition(position(), quote(), AGE(LIVE_QUOTE_FRESH_MS)).isFresh).toBe(true);
    expect(valuePosition(position(), quote(), AGE(LIVE_QUOTE_FRESH_MS + 1)).isFresh).toBe(false);
  });

  it('a quote stamped slightly ahead of the reader clock is fresh, not negatively aged', () => {
    const v = valuePosition(position(), quote(), AGE(-5_000));
    expect(v.isFresh).toBe(true);
    expect(v.ageMs).toBe(0);
  });

  it('an unparseable quoted_at yields an unknown age and therefore no freshness claim', () => {
    const v = valuePosition(position(), quote({ quotedAt: 'not a timestamp' }), NOW);
    expect(v.source).toBe('live'); // the mark is still the quote's
    expect(v.price).toBe(120);
    expect(v.ageMs).toBeNull();
    expect(v.isFresh).toBe(false);
  });

  it('freshness is PER TICKER: one frozen symbol, one ticking, same reference instant', () => {
    // No global "is the market open?" test could tell these apart — both rows exist, both are
    // mid-session, and only their own `quoted_at` distinguishes them.
    const at = Date.parse('2026-08-04T20:00:00.000Z');
    const ticking = valuePosition(position({ ticker: 'XLE' }), quote({ quotedAt: '2026-08-04T19:59:30.000Z' }), at);
    const frozen = valuePosition(position({ ticker: 'TLT' }), quote({ quotedAt: '2026-08-04T15:08:00.000Z' }), at);
    expect(ticking.isFresh).toBe(true);
    expect(frozen.isFresh).toBe(false);
    expect(frozen.source).toBe('live');
    expect(formatQuoteAge(frozen.ageMs)).toBe('4h');
  });

  it('a close is never fresh, whatever the instant — and !isFresh alone cannot mean "stale quote"', () => {
    const v = valuePosition(position(), undefined, Date.parse(METRICS_AS_OF) + 1_000);
    expect(v.source).toBe('close');
    // Even one second after the batch wrote it. A close is dated by its day and labelled a
    // close; `isFresh` is a claim only a live quote can earn, so a consumer must gate on
    // `source === 'live' && isFresh` rather than on `!isFresh`.
    expect(v.isFresh).toBe(false);
    expect(v.ageMs).toBe(1_000);
  });

  it('an unavailable valuation carries no freshness and no age', () => {
    const v = valuePosition(position({ entry_price: null }), quote(), NOW);
    expect(v.isFresh).toBe(false);
    expect(v.ageMs).toBeNull();
  });
});
