import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  assembleIntelligenceWhy,
  assembleMatrix,
  boardColumn,
  calendarWindow,
  getTodayEvents,
  getUpcomingEvents,
  localDateKey,
  normalizeKeyThemes,
  sortTodayBriefs,
  filterEventsToDay,
  getTradeIdeas,
  getTradeIdeaHistory,
} from './fetch';
import type {
  FxBriefRow,
  FxConfluenceSnapshotRow,
  FxConsensusSnapshotRow,
  FxEconomicCalendarRow,
  FxLedgerRow,
  MatrixCell,
} from './types';

/**
 * `economic_calendar` fixture for the #1753 window tests at the bottom of this file.
 * `vi.mock` is hoisted to the top of the module by Vitest, so it is declared here even
 * though only that block uses it: every other test in this file is a pure function and
 * never reaches the client.
 */
const calendarDb = vi.hoisted(() => ({
  rows: [] as { event_date: string }[],
  gte: [] as [string, string][],
  lte: [] as [string, string][],
}));

const tradeIdeasDb = vi.hoisted(() => ({
  selectColumns: '',
  gte: [] as [string, string][],
  lte: [] as [string, string][],
}));

vi.mock('./supabase', () => {
  type Payload = { data: unknown[] | null; error: unknown };
  interface TradeIdeasBuilder {
    select: (columns: string) => TradeIdeasBuilder;
    eq: (column: string, value: string) => TradeIdeasBuilder;
    gte: (column: string, value: string) => TradeIdeasBuilder;
    lte: (column: string, value: string) => TradeIdeasBuilder;
    order: (column: string, options?: unknown) => TradeIdeasBuilder;
    then: <T>(onFulfilled: (payload: Payload) => T) => Promise<T>;
  }
  const makeBuilder = (): TradeIdeasBuilder => {
    const builder: TradeIdeasBuilder = {
      select: (columns) => {
        tradeIdeasDb.selectColumns = columns;
        return builder;
      },
      eq: () => builder,
      gte: (column, value) => {
        tradeIdeasDb.gte.push([column, value]);
        return builder;
      },
      lte: (column, value) => {
        tradeIdeasDb.lte.push([column, value]);
        return builder;
      },
      order: () => builder,
      then: (onFulfilled) => Promise.resolve(onFulfilled({ data: [], error: null })),
    };
    return builder;
  };
  return {
    isTwelveXConfigured: () => true,
    twelveXSupabase: {
      from: (table: string): TradeIdeasBuilder => {
        if (table !== 'fx_trade_ideas_snapshot') throw new Error(`unexpected table: ${table}`);
        return makeBuilder();
      },
    },
  };
});

vi.mock('../supabase', () => {
  type Payload = { data: { event_date: string }[] | null; error: unknown };
  interface CalendarBuilder {
    select: (columns: string) => CalendarBuilder;
    order: (column: string, options?: unknown) => CalendarBuilder;
    gte: (column: string, value: string) => CalendarBuilder;
    lte: (column: string, value: string) => CalendarBuilder;
    then: <T>(onFulfilled: (payload: Payload) => T) => Promise<T>;
  }
  const makeBuilder = (): CalendarBuilder => {
    const bounds = { lo: '', hi: '' };
    const builder: CalendarBuilder = {
      select: () => builder,
      order: () => builder,
      gte: (column, value) => {
        calendarDb.gte.push([column, value]);
        bounds.lo = value;
        return builder;
      },
      lte: (column, value) => {
        calendarDb.lte.push([column, value]);
        bounds.hi = value;
        return builder;
      },
      // PostgREST applies .gte/.lte SERVER-side, so a row outside the requested window
      // never reaches the client. Emulating that is what makes these tests fail on a
      // wrong bound instead of passing on a fake that returns everything.
      then: (onFulfilled) =>
        Promise.resolve(
          onFulfilled({
            data: calendarDb.rows.filter(
              (r) => r.event_date >= bounds.lo && r.event_date <= bounds.hi,
            ),
            error: null,
          }),
        ),
    };
    return builder;
  };
  return {
    isSupabaseConfigured: () => true,
    supabase: {
      from: (table: string): CalendarBuilder => {
        if (table !== 'economic_calendar') throw new Error(`unexpected table: ${table}`);
        return makeBuilder();
      },
    },
  };
});

/**
 * `boardColumn` consolidates broker view currencies into the 8 G10 matrix
 * columns. dashboard owns this rule outright, so this table is the authoritative
 * statement of it — keep it exhaustive.
 */
describe('getTradeIdeas', () => {
  it('selects trade_levels and evidence alongside the core trade-idea columns', async () => {
    tradeIdeasDb.selectColumns = '';
    await getTradeIdeas('2026-06-24');
    expect(tradeIdeasDb.selectColumns).toContain('trade_levels');
    expect(tradeIdeasDb.selectColumns).toContain('evidence');
    expect(tradeIdeasDb.selectColumns).toContain('citations');
    expect(tradeIdeasDb.selectColumns).toContain('as_of');
  });
});

describe('getTradeIdeaHistory', () => {
  beforeEach(() => {
    tradeIdeasDb.selectColumns = '';
    tradeIdeasDb.gte = [];
    tradeIdeasDb.lte = [];
  });

  it('selects continuity columns with a run_date lower bound', async () => {
    await getTradeIdeaHistory(45);
    expect(tradeIdeasDb.selectColumns).toBe('run_date, pair, direction, as_of');
    expect(tradeIdeasDb.gte).toHaveLength(1);
    expect(tradeIdeasDb.gte[0][0]).toBe('run_date');
    expect(tradeIdeasDb.lte).toHaveLength(1);
    expect(tradeIdeasDb.lte[0][0]).toBe('run_date');
  });

  it('windows lookback relative to asOfBoardDate (inclusive)', async () => {
    await getTradeIdeaHistory(10, '2026-08-20');
    expect(tradeIdeasDb.gte).toEqual([['run_date', '2026-08-10']]);
    expect(tradeIdeasDb.lte).toEqual([['run_date', '2026-08-20']]);
  });
});

describe('boardColumn (currency consolidation)', () => {
  it('files a single G10 currency under itself', () => {
    expect(boardColumn('USD')).toBe('USD');
    expect(boardColumn('EUR')).toBe('EUR');
    expect(boardColumn('NZD')).toBe('NZD');
  });

  it('files a pair under its BASE (numerator) currency — no decomposition, no flip', () => {
    expect(boardColumn('EUR/USD')).toBe('EUR');
    expect(boardColumn('CAD/USD')).toBe('CAD');
    expect(boardColumn('GBP/JPY')).toBe('GBP');
  });

  it('keeps NOK/SEK as valid legs but never as columns', () => {
    expect(boardColumn('USD/SEK')).toBe('USD'); // Scandi quote leg is valid → base USD
    expect(boardColumn('EUR/NOK')).toBe('EUR');
    expect(boardColumn('NOK/SEK')).toBeNull(); // both legs valid, but base NOK has no column
  });

  it('drops any view with a leg outside the extended G10 set', () => {
    expect(boardColumn('USD/IDR')).toBeNull(); // exotic quote
    expect(boardColumn('EUR/TRY')).toBeNull();
    expect(boardColumn('XAU/USD')).toBeNull(); // gold, not a currency
  });

  it('drops non-currency / junk instruments', () => {
    expect(boardColumn('DXY')).toBeNull();
    expect(boardColumn('US10Y')).toBeNull();
    expect(boardColumn('GOLD')).toBeNull();
    expect(boardColumn('')).toBeNull();
  });

  it('normalizes case and surrounding whitespace', () => {
    expect(boardColumn('usd')).toBe('USD');
    expect(boardColumn('  eur/usd  ')).toBe('EUR');
  });
});

/**
 * `key_themes` arrives from Supabase in several shapes depending on whether the
 * column is jsonb or text[] and how the row was written. `normalizeKeyThemes`
 * must collapse every shape to a clean `string[]`. These lock that contract so
 * an upstream change can't silently regress the digest's theme chips.
 */
describe('normalizeKeyThemes', () => {
  it('passes through a jsonb / text[] array of strings', () => {
    expect(normalizeKeyThemes(['USD strength', 'ECB hawkish'])).toEqual([
      'USD strength',
      'ECB hawkish',
    ]);
  });

  it('coerces non-string array members to strings', () => {
    // jsonb arrays can carry numbers/booleans; they should stringify, not crash.
    expect(normalizeKeyThemes([1, true, 'x'] as unknown as string[])).toEqual([
      '1',
      'true',
      'x',
    ]);
  });

  it('drops empty and whitespace-only array entries', () => {
    expect(normalizeKeyThemes(['a', '', '   ', 'b'])).toEqual(['a', 'b']);
  });

  it('parses a JSON-encoded array string', () => {
    expect(normalizeKeyThemes('["a", "b"]')).toEqual(['a', 'b']);
  });

  it('trims before detecting a JSON-encoded array string', () => {
    expect(normalizeKeyThemes('  ["a","b"]  ')).toEqual(['a', 'b']);
  });

  it('treats a plain (non-JSON) string as a single theme', () => {
    expect(normalizeKeyThemes('EUR finding support')).toEqual(['EUR finding support']);
  });

  it('falls back to the raw string when a "[..." value is not valid JSON', () => {
    expect(normalizeKeyThemes('[unterminated')).toEqual(['[unterminated']);
  });

  it('returns [] for an empty or whitespace-only string', () => {
    expect(normalizeKeyThemes('')).toEqual([]);
    expect(normalizeKeyThemes('   ')).toEqual([]);
  });

  it('returns [] for null', () => {
    expect(normalizeKeyThemes(null)).toEqual([]);
  });

  it('treats a non-array JSON object string as a single raw theme', () => {
    // Only `[`-prefixed strings attempt a JSON-array parse; anything else is
    // taken verbatim as one theme rather than being dropped or mis-parsed.
    expect(normalizeKeyThemes('{"a":1}')).toEqual(['{"a":1}']);
  });
});

const brief = (over: Partial<FxBriefRow>): FxBriefRow => ({
  run_date: '2026-06-23', source_file: 's.pdf', source_url: null,
  document_title: null, broker_name: 'X', analyst_names: null,
  report_date: '2026-06-23', trader_relevance: 'low', central_thesis: null,
  brief_markdown: null, currency_views: [], risk_events: null,
  macro_themes: null, positioning_signals: null, ...over,
});

describe('sortTodayBriefs', () => {
  it('orders by relevance (high→low), then breadth, then newest report_date', () => {
    const lowOld = brief({ source_file: 'a', trader_relevance: 'low', report_date: '2026-06-20' });
    const highFew = brief({ source_file: 'b', trader_relevance: 'high', currency_views: [{ currency: 'USD', direction: 'bullish', conviction: 'high' }] });
    const highMany = brief({ source_file: 'c', trader_relevance: 'high', currency_views: [{ currency: 'USD', direction: 'bullish', conviction: 'high' }, { currency: 'EUR', direction: 'bearish', conviction: 'low' }] });
    const medNew = brief({ source_file: 'd', trader_relevance: 'medium', report_date: '2026-06-23' });
    const out = sortTodayBriefs([lowOld, highFew, highMany, medNew]).map((b) => b.source_file);
    expect(out).toEqual(['c', 'b', 'd', 'a']);
  });

  it('is stable and pure (does not mutate input)', () => {
    const input = [brief({ source_file: 'a' }), brief({ source_file: 'b' })];
    const copy = [...input];
    sortTodayBriefs(input);
    expect(input).toEqual(copy);
  });
});

const ev = (over: Partial<FxEconomicCalendarRow>): FxEconomicCalendarRow => ({
  id: 1, external_id: 'e', event_date: '2026-06-23', event_time: null,
  country: 'US', event_name: 'X', category: 'c', impact: 'low',
  actual: null, forecast: null, prior: null, event_datetime_utc: null, ...over,
});

describe('filterEventsToDay', () => {
  it('keeps only events whose local date equals the target key', () => {
    const todayUtc = ev({ id: 1, event_datetime_utc: '2026-06-23T14:30:00Z', event_date: '2026-06-23' });
    const tomorrow = ev({ id: 2, event_datetime_utc: '2026-06-24T14:30:00Z', event_date: '2026-06-24' });
    const allDayToday = ev({ id: 3, event_datetime_utc: null, event_date: '2026-06-23' });
    const key = '2026-06-23';
    const out = filterEventsToDay([todayUtc, tomorrow, allDayToday], key).map((e) => e.id);
    expect(out).toContain(1);
    expect(out).toContain(3);
    expect(out).not.toContain(2);
  });
});

const confluence = (over: Partial<FxConfluenceSnapshotRow>): FxConfluenceSnapshotRow => ({
  run_date: '2026-06-24', rank: 1, title: 'USD long', currency: 'USD',
  direction: 'long', score: 0.8,
  components: {
    consensus_strength: 0.84, event_alignment: 0.8, recency: 1.0, breadth: 0.85,
    n_brokers: 17, days_to_catalyst: 0, timeframe: '1-3M',
  },
  brief_keys: [], as_of: '2026-06-24T00:00:00Z', ...over,
});

const consensus = (over: Partial<FxConsensusSnapshotRow>): FxConsensusSnapshotRow => ({
  run_date: '2026-06-24', currency: 'USD', timeframe: 'medium', horizon_weeks: null,
  weighted: true, score: 1.1, confidence: 0.7, agreement: 0.66, tilt: 0.5,
  n_eff: 12, n_brokers: 17, n_views: 21,
  bullish_pct: 60, bearish_pct: 10, neutral_pct: 20, watch_pct: 10,
  as_of: '2026-06-24T00:00:00Z', ...over,
});

const ledger = (over: Partial<FxLedgerRow>): FxLedgerRow => ({
  run_date: '2026-06-24', source_file: 's.pdf', view_index: 0, broker_name: 'research Macro',
  currency: 'USD', direction: 'bullish', conviction: 'high', report_date: '2026-06-24',
  w_time: 1.0, w_event: 1.0, w_review: 0.9, relevance: 0.92, classification: 'active',
  reason: 'US rate resilience keeps the dollar bid.', as_of: '2026-06-24T00:00:00Z', ...over,
});

/**
 * `assembleIntelligenceWhy` is the PURE Tier-1/2/3 join behind the Intelligence
 * "why" panel: per confluence idea it pulls the score legs from `components`,
 * the canonical (medium/weighted) consensus decomposition, and the supporting
 * ledger desks for that currency. It must NOT surface w_time/w_event.
 */
describe('assembleIntelligenceWhy', () => {
  it('joins confluence + consensus + ledger desks per currency', () => {
    const out = assembleIntelligenceWhy(
      [confluence({ currency: 'USD', rank: 1 })],
      [consensus({ currency: 'USD' })],
      [ledger({ currency: 'USD', broker_name: 'research Macro' }), ledger({ currency: 'EUR', broker_name: 'Other' })],
      '2026-06-24'
    );
    expect(out.runDate).toBe('2026-06-24');
    expect(out.items).toHaveLength(1);
    const item = out.items[0];
    expect(item.currency).toBe('USD');
    expect(item.rank).toBe(1);
    expect(item.score).toBeCloseTo(0.8);
    // Tier 1 legs extracted from components jsonb.
    expect(item.components.consensus_strength).toBeCloseTo(0.84);
    expect(item.components.event_alignment).toBeCloseTo(0.8);
    expect(item.components.recency).toBeCloseTo(1.0);
    expect(item.components.breadth).toBeCloseTo(0.85);
    expect(item.components.n_brokers).toBe(17);
    expect(item.components.timeframe).toBe('1-3M');
    // Tier 2 consensus decomposition.
    expect(item.consensus?.score).toBeCloseTo(1.1);
    expect(item.consensus?.confidence).toBeCloseTo(0.7);
    expect(item.consensus?.bullish_pct).toBe(60);
    // Tier 3 desks — only the USD desk, NOT the EUR one.
    expect(item.desks).toHaveLength(1);
    expect(item.desks[0].broker).toBe('research Macro');
    expect(item.desks[0].classification).toBe('active');
    expect(item.desks[0].relevance).toBeCloseTo(0.92);
    expect(item.desks[0].reason).toBe('US rate resilience keeps the dollar bid.');
  });

  it('does NOT carry w_time / w_event onto assembled desks', () => {
    const out = assembleIntelligenceWhy(
      [confluence({ currency: 'USD' })],
      [consensus({ currency: 'USD' })],
      [ledger({ currency: 'USD' })],
      '2026-06-24'
    );
    const desk = out.items[0].desks[0] as unknown as Record<string, unknown>;
    expect('w_time' in desk).toBe(false);
    expect('w_event' in desk).toBe(false);
  });

  it('matches the BASE currency of a pair (EUR/USD → EUR consensus & desks)', () => {
    const out = assembleIntelligenceWhy(
      [confluence({ currency: 'EUR/USD', rank: 2 })],
      [consensus({ currency: 'EUR', score: -0.4 })],
      [ledger({ currency: 'EUR', broker_name: 'Harbour' })],
      '2026-06-24'
    );
    expect(out.items[0].consensus?.score).toBeCloseTo(-0.4);
    expect(out.items[0].desks).toHaveLength(1);
    expect(out.items[0].desks[0].broker).toBe('Harbour');
  });
});

/**
 * `assembleMatrix` is the PURE matrix assembly behind `getMatrix`: per
 * (broker, column), deduplicate exact (source_file, run_date), sort newest-first,
 * and split into primary + history. Tests must assert actual returned history
 * order and no duplicates.
 */
describe('assembleMatrix', () => {
  it('returns empty array when given no briefs', () => {
    const cells = assembleMatrix([]);
    expect(cells).toEqual([]);
  });

  it('creates one cell per (broker, column) with the newest view as primary', () => {
    const briefs = [
      brief({
        broker_name: 'research',
        run_date: '2026-06-24',
        source_file: 'research-latest.pdf',
        currency_views: [{ currency: 'USD', direction: 'bullish', conviction: 'high' }],
      }),
      brief({
        broker_name: 'Meridian',
        run_date: '2026-06-24',
        source_file: 'meridian-latest.pdf',
        currency_views: [{ currency: 'EUR', direction: 'bearish', conviction: 'medium' }],
      }),
    ];
    const cells = assembleMatrix(briefs);
    expect(cells).toHaveLength(2);
    const research = cells.find((c) => c.broker === 'research' && c.column === 'USD');
    expect(research).toBeDefined();
    expect(research!.direction).toBe('bullish');
    expect(research!.run_date).toBe('2026-06-24');
    const meridian = cells.find((c) => c.broker === 'Meridian' && c.column === 'EUR');
    expect(meridian).toBeDefined();
    expect(meridian!.direction).toBe('bearish');
  });

  it('deduplicates exact (source_file, run_date) pairs keeping only first occurrence', () => {
    const briefs = [
      brief({
        broker_name: 'research',
        run_date: '2026-06-24',
        source_file: 'research-duplicate.pdf',
        currency_views: [{ currency: 'USD', direction: 'bullish', conviction: 'high' }],
      }),
      brief({
        broker_name: 'research',
        run_date: '2026-06-24',
        source_file: 'research-duplicate.pdf', // exact duplicate
        currency_views: [{ currency: 'USD', direction: 'bullish', conviction: 'high' }],
      }),
    ];
    const cells = assembleMatrix(briefs);
    expect(cells).toHaveLength(1);
    expect(cells[0].history).toBeUndefined();
  });

  it('preserves distinct views as history sorted newest-first', () => {
    const briefs = [
      brief({
        broker_name: 'research',
        run_date: '2026-06-24',
        source_file: 'research-2026-06-24.pdf',
        currency_views: [{ currency: 'USD', direction: 'bullish', conviction: 'high', rationale: 'Latest view' }],
      }),
      brief({
        broker_name: 'research',
        run_date: '2026-06-23',
        source_file: 'research-2026-06-23.pdf',
        currency_views: [{ currency: 'USD', direction: 'bullish', conviction: 'medium', rationale: 'Previous view' }],
      }),
      brief({
        broker_name: 'research',
        run_date: '2026-06-22',
        source_file: 'research-2026-06-22.pdf',
        currency_views: [{ currency: 'USD', direction: 'neutral', conviction: 'low', rationale: 'Oldest view' }],
      }),
    ];
    const cells = assembleMatrix(briefs);
    expect(cells).toHaveLength(1);
    const cell = cells[0];
    expect(cell.run_date).toBe('2026-06-24');
    expect(cell.rationale).toBe('Latest view');
    expect(cell.history).toHaveLength(2);
    expect(cell.history![0].run_date).toBe('2026-06-23');
    expect(cell.history![0].rationale).toBe('Previous view');
    expect(cell.history![1].run_date).toBe('2026-06-22');
    expect(cell.history![1].rationale).toBe('Oldest view');
  });

  it('files pairs under their base currency only (EUR/USD → EUR column)', () => {
    const briefs = [
      brief({
        broker_name: 'research',
        run_date: '2026-06-24',
        source_file: 'research.pdf',
        currency_views: [{ currency: 'EUR/USD', direction: 'bullish', conviction: 'high' }],
      }),
    ];
    const cells = assembleMatrix(briefs);
    expect(cells).toHaveLength(1);
    expect(cells[0].column).toBe('EUR');
    expect(cells[0].currency).toBe('EUR/USD'); // verbatim for display
  });

  it('drops views outside the extended G10 set', () => {
    const briefs = [
      brief({
        broker_name: 'research',
        run_date: '2026-06-24',
        source_file: 'research.pdf',
        currency_views: [
          { currency: 'USD', direction: 'bullish', conviction: 'high' },
          { currency: 'USD/TRY', direction: 'bearish', conviction: 'high' }, // exotic
          { currency: 'DXY', direction: 'bullish', conviction: 'high' }, // not a currency
        ],
      }),
    ];
    const cells = assembleMatrix(briefs);
    expect(cells).toHaveLength(1);
    expect(cells[0].currency).toBe('USD'); // only the USD view survived
  });
});

describe('assembleIntelligenceWhy continued', () => {
  it('orders desks by relevance descending', () => {
    const out = assembleIntelligenceWhy(
      [confluence({ currency: 'USD' })],
      [consensus({ currency: 'USD' })],
      [
        ledger({ currency: 'USD', broker_name: 'Low', relevance: 0.4 }),
        ledger({ currency: 'USD', broker_name: 'High', relevance: 0.92 }),
        ledger({ currency: 'USD', broker_name: 'Mid', relevance: 0.7 }),
      ],
      '2026-06-24'
    );
    expect(out.items[0].desks.map((d) => d.broker)).toEqual(['High', 'Mid', 'Low']);
  });

  it('yields a null consensus when no matching consensus row exists', () => {
    const out = assembleIntelligenceWhy(
      [confluence({ currency: 'JPY' })],
      [consensus({ currency: 'USD' })],
      [],
      '2026-06-24'
    );
    expect(out.items[0].consensus).toBeNull();
    expect(out.items[0].desks).toEqual([]);
  });

  it('coerces a null components jsonb to zeroed legs and null counts (no NaN)', () => {
    // Real Supabase payloads can carry a null jsonb; extractWhyComponents must
    // treat it as {} → [0,1] legs default to 0, counts to null, timeframe null.
    const out = assembleIntelligenceWhy(
      [confluence({ currency: 'USD', components: null as unknown as Record<string, unknown> })],
      [],
      [],
      '2026-06-24'
    );
    const c = out.items[0].components;
    expect(c.consensus_strength).toBe(0);
    expect(c.event_alignment).toBe(0);
    expect(c.recency).toBe(0);
    expect(c.breadth).toBe(0);
    expect(Number.isNaN(c.consensus_strength)).toBe(false);
    expect(c.n_brokers).toBeNull();
    expect(c.days_to_catalyst).toBeNull();
    expect(c.timeframe).toBeNull();
  });

  it('defaults missing component legs to 0 / null when components is an empty object', () => {
    const out = assembleIntelligenceWhy(
      [confluence({ currency: 'USD', components: {} })],
      [],
      [],
      '2026-06-24'
    );
    const c = out.items[0].components;
    expect(c.consensus_strength).toBe(0);
    expect(c.event_alignment).toBe(0);
    expect(c.recency).toBe(0);
    expect(c.breadth).toBe(0);
    expect(c.n_brokers).toBeNull();
    expect(c.days_to_catalyst).toBeNull();
    expect(c.timeframe).toBeNull();
  });

  it('treats a non-object components jsonb (array / primitive) as empty → safe defaults', () => {
    // The object-guard rejects arrays and primitives the same way it handles {}:
    // every leg falls back to its [0,1] default of 0, counts to null. This pins
    // the guard so a refactor can't let a stray `[...]`/string index leak in.
    const out = assembleIntelligenceWhy(
      [
        confluence({ currency: 'USD', rank: 1, components: [1, 2, 3] as unknown as Record<string, unknown> }),
        confluence({ currency: 'EUR', rank: 2, components: 'garbage' as unknown as Record<string, unknown> }),
      ],
      [],
      [],
      '2026-06-24'
    );
    for (const it of out.items) {
      const c = it.components;
      expect(c.consensus_strength).toBe(0);
      expect(c.event_alignment).toBe(0);
      expect(c.recency).toBe(0);
      expect(c.breadth).toBe(0);
      expect(c.n_brokers).toBeNull();
      expect(c.days_to_catalyst).toBeNull();
      expect(c.timeframe).toBeNull();
    }
  });

  it('coerces string-numeric legs and rejects garbage to 0 / null (never NaN)', () => {
    // jsonb can deliver numbers as strings; finite string-numbers coerce, but
    // non-finite garbage (NaN, non-numeric strings) must NOT leak through.
    const out = assembleIntelligenceWhy(
      [
        confluence({
          currency: 'USD',
          components: {
            consensus_strength: '0.84', // string number → coerces to 0.84
            event_alignment: 'nope', // garbage → 0
            recency: '', // empty string → Number('') is 0 (finite) → 0
            breadth: NaN, // explicit NaN → 0
            n_brokers: '17', // string number → 17
            days_to_catalyst: 'soon', // garbage count → null (not NaN)
            timeframe: '   ', // whitespace-only → null
          },
        }),
      ],
      [],
      [],
      '2026-06-24'
    );
    const c = out.items[0].components;
    expect(c.consensus_strength).toBeCloseTo(0.84);
    expect(c.event_alignment).toBe(0);
    expect(c.recency).toBe(0);
    expect(c.breadth).toBe(0);
    expect(Number.isNaN(c.breadth)).toBe(false);
    expect(c.n_brokers).toBe(17);
    expect(c.days_to_catalyst).toBeNull();
    expect(c.timeframe).toBeNull();
  });

  it('preserves confluence rank order', () => {
    const out = assembleIntelligenceWhy(
      [
        confluence({ currency: 'JPY', rank: 2 }),
        confluence({ currency: 'USD', rank: 1 }),
      ],
      [],
      [],
      '2026-06-24'
    );
    expect(out.items.map((i) => i.rank)).toEqual([1, 2]);
  });
});

/* ------------------------------------------------------------------ *
 * #1753 — the calendar window: UTC bound vs viewer-local key
 * ------------------------------------------------------------------ */

const REAL_TZ = process.env.TZ;

/**
 * Pin the viewer's zone AND the wall clock. Node invalidates V8's cached default
 * timezone when `process.env.TZ` is assigned, so a formatter constructed afterwards
 * resolves to `zone`; the assertion makes a runtime that ignores the assignment fail
 * loudly here rather than silently testing the runner's own zone (CI runs in UTC).
 */
function useViewer(zone: string, isoInstant: string): void {
  process.env.TZ = zone;
  vi.setSystemTime(new Date(isoInstant));
  expect(new Intl.DateTimeFormat().resolvedOptions().timeZone).toBe(zone);
}

describe('localDateKey / calendarWindow (PURE)', () => {
  it('keys an instant to the calendar day of the given zone, not of UTC', () => {
    // 01:30Z on Aug 1 is still Jul 31 in New York and already Aug 1 in Auckland.
    const instant = new Date('2026-08-01T01:30:00Z');
    expect(localDateKey(instant, 'America/New_York')).toBe('2026-07-31');
    expect(localDateKey(instant, 'Pacific/Auckland')).toBe('2026-08-01');
    expect(localDateKey(instant, 'UTC')).toBe('2026-08-01');
  });

  it('pads the query window one day either side of the local 14-day window', () => {
    const w = calendarWindow(new Date('2026-08-01T01:30:00Z'), 'America/New_York');
    // The promise the surface makes: local today → +14 days.
    expect(w.localStart).toBe('2026-07-31');
    expect(w.localEnd).toBe('2026-08-14');
    // The bound sent to PostgREST, padded because `event_date` is a wall-clock day and
    // can sit a day either side of the local key derived from the release instant.
    expect(w.queryStart).toBe('2026-07-30');
    expect(w.queryEnd).toBe('2026-08-15');
  });

  it('is the same construction eventLocalDateKey uses, so keys are comparable', () => {
    process.env.TZ = 'America/New_York';
    try {
      const iso = '2026-08-01T01:30:00Z';
      const kept = filterEventsToDay(
        [ev({ id: 1, event_datetime_utc: iso, event_date: '2026-08-01' })],
        localDateKey(new Date(iso))
      );
      expect(kept).toHaveLength(1);
    } finally {
      if (REAL_TZ === undefined) delete process.env.TZ;
      else process.env.TZ = REAL_TZ;
    }
  });
});

describe('getTodayEvents / getUpcomingEvents over the mocked calendar', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    calendarDb.rows = [];
    calendarDb.gte = [];
    calendarDb.lte = [];
  });

  afterEach(() => {
    vi.useRealTimers();
    if (REAL_TZ === undefined) delete process.env.TZ;
    else process.env.TZ = REAL_TZ;
  });

  it('#1753 REGRESSION: a western viewer still sees their local-today releases', async () => {
    // 21:30 Jul 31 in New York = 01:30 Aug 1 UTC. Before the fix the predicate was built
    // from the UTC date ('2026-08-01'), so this row — the viewer's own today — was
    // dropped by PostgREST before filterEventsToDay could keep it, and the Today tab's
    // events strip went blank while the row existed.
    useViewer('America/New_York', '2026-08-01T01:30:00Z');
    calendarDb.rows = [
      ev({ id: 1, event_date: '2026-07-31', event_datetime_utc: '2026-07-31T22:00:00Z' }),
      ev({ id: 2, event_date: '2026-08-03', event_datetime_utc: '2026-08-03T12:30:00Z' }),
    ];
    const today = await getTodayEvents();
    expect(today.map((e) => e.id)).toEqual([1]);
    expect(calendarDb.gte).toEqual([['event_date', '2026-07-30']]);
    expect(calendarDb.lte).toEqual([['event_date', '2026-08-15']]);
  });

  it('keys all-day rows (no release instant) by their wall-clock event_date', async () => {
    useViewer('America/New_York', '2026-08-01T01:30:00Z');
    calendarDb.rows = [
      ev({ id: 3, event_date: '2026-07-31', event_datetime_utc: null }),
      ev({ id: 4, event_date: '2026-08-01', event_datetime_utc: null }),
    ];
    expect((await getTodayEvents()).map((e) => e.id)).toEqual([3]);
  });

  it('drops local-yesterday rows from "upcoming" though the query pads back a day', async () => {
    useViewer('America/New_York', '2026-08-01T01:30:00Z');
    calendarDb.rows = [
      // 18:00Z Jul 30 = 14:00 local Jul 30 — inside the padded query, local-yesterday.
      ev({ id: 5, event_date: '2026-07-30', event_datetime_utc: '2026-07-30T18:00:00Z' }),
      ev({ id: 6, event_date: '2026-07-31', event_datetime_utc: '2026-07-31T22:00:00Z' }),
    ];
    expect((await getUpcomingEvents()).map((e) => e.id)).toEqual([6]);
  });

  it('keeps a row whose event_date is past the horizon but whose local day is not', async () => {
    useViewer('America/New_York', '2026-08-01T01:30:00Z');
    calendarDb.rows = [
      // 02:00Z Aug 15 = 22:00 local Aug 14 — the last local day of the window, and the
      // reason queryEnd is padded forward.
      ev({ id: 7, event_date: '2026-08-15', event_datetime_utc: '2026-08-15T02:00:00Z' }),
      // 12:30Z Aug 15 = 08:30 local Aug 15 — genuinely past the 14-day horizon.
      ev({ id: 8, event_date: '2026-08-15', event_datetime_utc: '2026-08-15T12:30:00Z' }),
    ];
    expect((await getUpcomingEvents()).map((e) => e.id)).toEqual([7]);
  });

  it('holds for an eastern viewer whose local day runs ahead of UTC', async () => {
    // 12:30 Aug 1 in Auckland = 00:30 Aug 1 UTC. The 23:00Z Jul 31 release is already
    // Aug 1 locally, so it belongs to this viewer's today; the 09:00Z one is Jul 31.
    useViewer('Pacific/Auckland', '2026-08-01T00:30:00Z');
    calendarDb.rows = [
      ev({ id: 9, event_date: '2026-07-31', event_datetime_utc: '2026-07-31T23:00:00Z' }),
      ev({ id: 10, event_date: '2026-07-31', event_datetime_utc: '2026-07-31T09:00:00Z' }),
    ];
    expect((await getTodayEvents()).map((e) => e.id)).toEqual([9]);
    expect((await getUpcomingEvents()).map((e) => e.id)).toEqual([9]);
  });
});
