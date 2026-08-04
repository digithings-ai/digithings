import { describe, expect, it } from 'vitest';
import {
  liveQuoteFromRow,
  mergeQuotes,
  normalizeTimestamptz,
  valuePosition,
  type LiveQuote,
  type LiveQuoteMap,
  type ValuablePosition,
} from './live-valuation';

const QUOTED_AT = '2026-08-03T18:23:00.000Z';
const METRICS_AS_OF = '2026-07-31T20:00:00.000Z';

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
    const v = valuePosition(position(), quote());
    expect(v.source).toBe('live');
    expect(v.price).toBe(120);
    expect(v.asOf).toBe(QUOTED_AT);
    // Computed against entry (100 → 120), NOT the stored 10 that belongs to the close.
    expect(v.unrealizedPct).toBeCloseTo(20, 10);
  });

  it('close is used when there is no live row, labelled as a close', () => {
    const v = valuePosition(position(), undefined);
    expect(v.source).toBe('close');
    expect(v.price).toBe(110);
    expect(v.asOf).toBe(METRICS_AS_OF);
  });

  it('close prefers the STORED unrealized_pnl_pct over recomputing (it is the record)', () => {
    // Recomputing 100 → 110 would give 10.0; the record says 9.87 (the batch resolved its
    // own basis). The persisted series wins so the overlay cannot disagree with it.
    const v = valuePosition(position({ unrealized_pnl_pct: 9.87 }), null);
    expect(v.source).toBe('close');
    expect(v.unrealizedPct).toBe(9.87);
  });

  it('close recomputes only when the record carries no percentage', () => {
    const v = valuePosition(position({ unrealized_pnl_pct: null }), null);
    expect(v.source).toBe('close');
    expect(v.unrealizedPct).toBeCloseTo(10, 10);
  });

  it('unavailable when neither lane has anything — never 0, never a midpoint', () => {
    const v = valuePosition(position({ current_price: null, metrics_as_of: null }), undefined);
    expect(v).toEqual({ source: 'unavailable', price: null, unrealizedPct: null, asOf: null });
  });

  it('unavailable when the close has a price but no metrics_as_of (an unattributed close)', () => {
    const v = valuePosition(position({ metrics_as_of: null }), undefined);
    expect(v.source).toBe('unavailable');
  });

  it('a non-positive live mark (halted symbol) falls through to the close, not to −100%', () => {
    // Migration 063 declined a `price > 0` CHECK because Finnhub returns 0 for a halted or
    // unrecognised symbol and leaves consumers to gate on the value.
    const v = valuePosition(position(), quote({ price: 0 }));
    expect(v.source).toBe('close');
    expect(v.unrealizedPct).toBe(10);
  });
});

describe('valuePosition — entry basis guard (no Infinity, no NaN)', () => {
  for (const entry of [null, 0, -12.5] as const) {
    it(`unavailable when entry_price is ${String(entry)}`, () => {
      const withLive = valuePosition(position({ entry_price: entry }), quote());
      const withCloseOnly = valuePosition(position({ entry_price: entry }), undefined);
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
    expect(valuePosition(cash, undefined).source).toBe('unavailable');
    // Explicit even if the sleeve were ever handed a price and a basis: it is a NAV split
    // line, not an instrument.
    expect(valuePosition({ ...cash, entry_price: 1, current_price: 1 }, quote()).source).toBe(
      'unavailable'
    );
    expect(valuePosition({ ...cash, ticker: ' cash ' }, undefined).source).toBe('unavailable');
  });
});

describe('valuePosition — scale and immutability', () => {
  it('unrealizedPct is in PERCENT POINTS: 1.24, not 0.0124 (matches change_pct)', () => {
    const v = valuePosition(position({ entry_price: 100 }), quote({ price: 101.24 }));
    expect(v.unrealizedPct).toBeCloseTo(1.24, 10);
    expect(v.unrealizedPct).not.toBeCloseTo(0.0124, 6);
  });

  it('a negative move is a negative percentage, not an absolute one', () => {
    const v = valuePosition(position({ entry_price: 200 }), quote({ price: 150 }));
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
    const v = valuePosition(p, q);

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
    const a = valuePosition(position({ entry_price: null }), undefined);
    const b = valuePosition(position({ entry_price: null }), undefined);
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
