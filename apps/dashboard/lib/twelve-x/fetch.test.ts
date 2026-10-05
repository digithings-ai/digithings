import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  assembleIntelligenceWhy,
  assembleMatrix,
  boardColumn,
  calendarWindow,
  getIdeaEval,
  getTodayEvents,
  getUpcomingEvents,
  localDateKey,
  normalizeKeyThemes,
  sortTodayBriefs,
  filterEventsToDay,
  getTradeIdeas,
  getTradeIdeaArchive,
  getTradeIdeaHistory,
  getFxFixSeries,
  getConsensusTimeSeries,
  computeConsensusDeltaSet,
} from './fetch';
import type {
  FxBriefRow,
  FxConfluenceSnapshotRow,
  FxConsensusSnapshotRow,
  FxEconomicCalendarRow,
  FxIdeaEvalRow,
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
  eq: [] as [string, string][],
  order: [] as [string, unknown][],
  limits: [] as number[],
  /** One entry per query, consumed in order. Exhausted → empty result. */
  responses: [] as { data: unknown[]; error: unknown }[],
}));

const ideaEvalDb = vi.hoisted(() => ({
  rows: [] as Partial<FxIdeaEvalRow>[],
}));

const macroDb = vi.hoisted(() => ({
  rows: [] as { series_id: string; obs_date: string; value: number | null }[],
}));

/**
 * `fx_consensus_snapshot` fixture for the DIG-57 leaf 3 generation dedupe.
 * `queries` records one entry per AWAITED read of this table, so a test can prove
 * the client-side generation filter costs no extra round trip.
 */
const consensusDb = vi.hoisted(() => ({
  rows: [] as Partial<FxConsensusSnapshotRow>[],
  queries: [] as { columns: string; eq: [string, string | boolean][] }[],
}));

vi.mock('./supabase', () => {
  type Payload = { data: unknown[] | null; error: unknown };
  interface TradeIdeasBuilder {
    select: (columns: string) => TradeIdeasBuilder;
    eq: (column: string, value: string) => TradeIdeasBuilder;
    gte: (column: string, value: string) => TradeIdeasBuilder;
    lte: (column: string, value: string) => TradeIdeasBuilder;
    order: (column: string, options?: unknown) => TradeIdeasBuilder;
    limit: (count: number) => TradeIdeasBuilder;
    then: <T>(onFulfilled: (payload: Payload) => T) => Promise<T>;
  }
  interface ConsensusBuilder {
    select: (columns: string) => ConsensusBuilder;
    eq: (column: string, value: string | boolean) => ConsensusBuilder;
    order: (column: string, options?: unknown) => ConsensusBuilder;
    then: <T>(onFulfilled: (payload: Payload) => T) => Promise<T>;
  }
  const makeBuilder = (): TradeIdeasBuilder => {
    const builder: TradeIdeasBuilder = {
      select: (columns) => {
        tradeIdeasDb.selectColumns = columns;
        return builder;
      },
      eq: (column, value) => {
        tradeIdeasDb.eq.push([column, value]);
        return builder;
      },
      gte: (column, value) => {
        tradeIdeasDb.gte.push([column, value]);
        return builder;
      },
      lte: (column, value) => {
        tradeIdeasDb.lte.push([column, value]);
        return builder;
      },
      order: (column, options) => {
        tradeIdeasDb.order.push([column, options]);
        return builder;
      },
      limit: (count) => {
        tradeIdeasDb.limits.push(count);
        return builder;
      },
      then: (onFulfilled) =>
        Promise.resolve(
          onFulfilled(tradeIdeasDb.responses.shift() ?? { data: [], error: null }),
        ),
    };
    return builder;
  };
  const makeIdeaEvalBuilder = (): TradeIdeasBuilder => {
    const builder: TradeIdeasBuilder = {
      select: () => builder,
      eq: () => builder,
      gte: () => builder,
      lte: () => builder,
      order: () => builder,
      then: (onFulfilled) =>
        Promise.resolve(onFulfilled({ data: ideaEvalDb.rows, error: null })),
    };
    return builder;
  };
  const makeConsensusBuilder = (): ConsensusBuilder => {
    const query: { columns: string; eq: [string, string | boolean][] } = { columns: '', eq: [] };
    const builder: ConsensusBuilder = {
      select: (columns) => {
        query.columns = columns;
        return builder;
      },
      eq: (column, value) => {
        query.eq.push([column, value]);
        return builder;
      },
      order: () => builder,
      // PostgREST applies .eq SERVER-side, so emulating it keeps the fixture honest:
      // an unweighted or other-timeframe row never reaches the client, and the
      // one-round-trip assertion cannot be satisfied by a second filtered read.
      then: (onFulfilled) => {
        consensusDb.queries.push(query);
        return Promise.resolve(
          onFulfilled({
            data: consensusDb.rows.filter((r) =>
              query.eq.every(([column, value]) => {
                const row = r as unknown as Record<string, unknown>;
                return row[column] === value;
              }),
            ),
            error: null,
          }),
        );
      },
    };
    return builder;
  };
  return {
    isTwelveXConfigured: () => true,
    twelveXSupabase: {
      from: (table: string): TradeIdeasBuilder | ConsensusBuilder => {
        if (table === 'fx_idea_eval') return makeIdeaEvalBuilder();
        if (table === 'fx_consensus_snapshot') return makeConsensusBuilder();
        if (table !== 'fx_trade_ideas_snapshot') throw new Error(`unexpected table: ${table}`);
        return makeBuilder();
      },
    },
  };
});

vi.mock('../supabase', () => {
  type Payload = { data: unknown[] | null; error: unknown };
  interface CalendarBuilder {
    select: (columns: string) => CalendarBuilder;
    order: (column: string, options?: unknown) => CalendarBuilder;
    gte: (column: string, value: string) => CalendarBuilder;
    lte: (column: string, value: string) => CalendarBuilder;
    in: (column: string, values: string[]) => CalendarBuilder;
    limit: (count: number) => CalendarBuilder;
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
      in: () => builder,
      limit: () => builder,
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
  const makeMacroBuilder = (): CalendarBuilder => {
    let ids: string[] = [];
    let lo = '';
    const builder: CalendarBuilder = {
      select: () => builder,
      order: () => builder,
      gte: (column, value) => {
        if (column === 'obs_date') lo = value;
        return builder;
      },
      lte: () => builder,
      in: (_column, values) => {
        ids = values;
        return builder;
      },
      limit: () => builder,
      then: (onFulfilled) =>
        Promise.resolve(
          onFulfilled({
            data: macroDb.rows.filter(
              (r) => ids.includes(r.series_id) && r.obs_date >= lo,
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
        if (table === 'macro_series_observations') return makeMacroBuilder();
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
  beforeEach(() => {
    tradeIdeasDb.selectColumns = '';
    tradeIdeasDb.eq = [];
    tradeIdeasDb.gte = [];
    tradeIdeasDb.lte = [];
    tradeIdeasDb.order = [];
    tradeIdeasDb.limits = [];
    tradeIdeasDb.responses = [];
  });

  it('selects trade_levels and evidence alongside the core trade-idea columns', async () => {
    await getTradeIdeas('2026-06-24');
    expect(tradeIdeasDb.selectColumns).toContain('trade_levels');
    expect(tradeIdeasDb.selectColumns).toContain('evidence');
    expect(tradeIdeasDb.selectColumns).toContain('citations');
    expect(tradeIdeasDb.selectColumns).toContain('as_of');
    expect(tradeIdeasDb.selectColumns).toContain('timeframe');
    expect(tradeIdeasDb.selectColumns).toContain('idea_id');
  });

  it('reads the board by exact run_date and does not query further when it has rows', async () => {
    tradeIdeasDb.responses = [
      { data: [{ run_date: '2026-09-28', rank: 1, idea_id: 'fresh' }], error: null },
    ];

    const rows = await getTradeIdeas('2026-09-28');

    expect(rows).toHaveLength(1);
    expect(tradeIdeasDb.eq).toEqual([['run_date', '2026-09-28']]);
    // Exactly one query — the fallback never runs when today's board is populated.
    expect(tradeIdeasDb.lte).toEqual([]);
  });

  it('falls back to episodes refreshed today but keyed to an earlier board date', async () => {
    // A continued episode is written back to its ORIGIN run_date, so the exact-date
    // query for today comes back empty even though today's publish refreshed it.
    tradeIdeasDb.responses = [
      { data: [], error: null },
      {
        data: [
          {
            run_date: '2026-09-24',
            rank: 1,
            pair: 'EUR/USD',
            direction: 'short',
            idea_id: 'carried-episode',
            as_of: '2026-09-28T22:26:56+00:00',
          },
        ],
        error: null,
      },
    ];

    const rows = await getTradeIdeas('2026-09-28');

    expect(rows).toHaveLength(1);
    expect(rows[0].idea_id).toBe('carried-episode');
    // Bounded to boards on/before today, newest-refresh-first with headroom past
    // the board cap (the limit applies pre-dedupe), and NO clock-midnight bound —
    // "today's publish" is anchored to the last-publish instant in code, not SQL.
    expect(tradeIdeasDb.lte).toEqual([['run_date', '2026-09-28']]);
    expect(tradeIdeasDb.gte).toEqual([]);
    expect(tradeIdeasDb.order).toContainEqual(['as_of', { ascending: false }]);
    expect(tradeIdeasDb.limits).toEqual([50]);
  });

  it('keeps only the newest row per episode in the fallback', async () => {
    tradeIdeasDb.responses = [
      { data: [], error: null },
      {
        // Newest-refresh-first, as the fallback query orders them.
        data: [
          { run_date: '2026-09-25', rank: 2, pair: 'EUR/USD', direction: 'short', idea_id: 'ep-1', as_of: '2026-09-28T22:26:00+00:00' },
          { run_date: '2026-09-24', rank: 1, pair: 'EUR/USD', direction: 'short', idea_id: 'ep-1', as_of: '2026-09-28T22:25:00+00:00' },
          { run_date: '2026-09-24', rank: 2, pair: 'USD/JPY', direction: 'long', idea_id: 'ep-2', as_of: '2026-09-28T22:24:00+00:00' },
        ],
        error: null,
      },
    ];

    const rows = await getTradeIdeas('2026-09-28');

    expect(rows.map((r) => r.idea_id)).toEqual(['ep-1', 'ep-2']);
  });

  it('stays empty when nothing published since the board date began', async () => {
    // The latest publish is yesterday's — a closed-episode day must never
    // resurface stale rows, even though boards on/before today exist.
    tradeIdeasDb.responses = [
      { data: [], error: null },
      {
        data: [
          { run_date: '2026-09-24', rank: 1, pair: 'EUR/USD', direction: 'short', idea_id: 'stale', as_of: '2026-09-27T22:26:00+00:00' },
        ],
        error: null,
      },
    ];

    expect(await getTradeIdeas('2026-09-28')).toEqual([]);
  });

  it('counts a publish that crossed UTC midnight as the run it belongs to', async () => {
    // Late run for the 28th published at 00:10Z on the 29th: the rows satisfy a
    // next-day clock bound, but the last-publish anchor keeps them on the 28th's
    // board — and off the 29th's until the 29th publishes for real.
    tradeIdeasDb.responses = [
      { data: [], error: null },
      {
        data: [
          { run_date: '2026-09-24', rank: 1, pair: 'EUR/USD', direction: 'short', idea_id: 'late', as_of: '2026-09-29T00:10:00+00:00' },
        ],
        error: null,
      },
    ];

    const rows = await getTradeIdeas('2026-09-28');

    expect(rows.map((r) => r.idea_id)).toEqual(['late']);
  });

  it('keeps only the latest publish batch, then caps the board', async () => {
    const batch = Array.from({ length: 11 }, (_, i) => ({
      run_date: '2026-09-24',
      rank: i + 1,
      pair: `PAIR${i}`,
      direction: 'long',
      idea_id: `batch-${i}`,
      as_of: '2026-09-28T22:26:00+00:00',
    }));
    tradeIdeasDb.responses = [
      { data: [], error: null },
      {
        data: [
          ...batch,
          // An older publish's row inside the over-fetch window: outside the
          // batch grace, so it must not displace (or join) today's board.
          { run_date: '2026-09-23', rank: 1, pair: 'OLD', direction: 'short', idea_id: 'old-batch', as_of: '2026-09-28T21:00:00+00:00' },
        ],
        error: null,
      },
    ];

    const rows = await getTradeIdeas('2026-09-28');

    expect(rows).toHaveLength(10);
    expect(rows.map((r) => r.idea_id)).not.toContain('old-batch');
  });

  it('stays empty when the board date never published', async () => {
    const rows = await getTradeIdeas('2026-09-28');

    expect(rows).toEqual([]);
  });
});

describe('getTradeIdeaArchive', () => {
  beforeEach(() => {
    tradeIdeasDb.selectColumns = '';
    tradeIdeasDb.order = [];
  });

  it('selects full idea columns newest-board-first for the Trades history table', async () => {
    await getTradeIdeaArchive();
    expect(tradeIdeasDb.selectColumns).toContain('trade_levels');
    expect(tradeIdeasDb.selectColumns).toContain('thesis');
    expect(tradeIdeasDb.selectColumns).toContain('catalyst');
    // Same board columns as getTradeIdeas (idea identity included) so
    // archive↔board joins on episode identity never miss.
    expect(tradeIdeasDb.selectColumns).toContain('idea_id');
    expect(tradeIdeasDb.selectColumns).toContain('timeframe');
    expect(tradeIdeasDb.order[0]).toEqual(['run_date', { ascending: false }]);
    expect(tradeIdeasDb.order[1]).toEqual(['rank', { ascending: true }]);
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

describe('getIdeaEval netCarried option', () => {
  const carried = (run_date: string): Partial<FxIdeaEvalRow> => ({
    run_date,
    rank: 1,
    horizon_days: 0,
    pair: 'EUR/USD',
    direction: 'long',
    status: 'carried',
    as_of: '2026-06-26T00:00:00Z',
  });

  beforeEach(() => {
    ideaEvalDb.rows = [carried('2026-06-19'), carried('2026-06-26')];
  });

  afterEach(() => {
    ideaEvalDb.rows = [];
  });

  it('nets same-axis carried boards by default (Trades board)', async () => {
    const rows = await getIdeaEval();
    expect(rows).toHaveLength(1);
    expect(rows[0].run_date).toBe('2026-06-26');
  });

  it('returns raw rows with netCarried:false (honest track-record carried count)', async () => {
    const rows = await getIdeaEval({ netCarried: false });
    expect(rows).toHaveLength(2);
    expect(rows.filter((r) => r.status === 'carried')).toHaveLength(2);
  });
});

describe('getFxFixSeries', () => {
  beforeEach(() => {
    macroDb.rows = [
      { series_id: 'FX/EUR', obs_date: '2026-06-16', value: 1.1 },
      { series_id: 'FX/EUR', obs_date: '2026-06-17', value: 1.2 },
      { series_id: 'FX/JPY', obs_date: '2026-06-16', value: 150 },
      { series_id: 'FX/JPY', obs_date: '2026-06-17', value: 151 },
      { series_id: 'VIXCLS', obs_date: '2026-06-17', value: 15 },
    ];
  });

  afterEach(() => {
    macroDb.rows = [];
  });

  it('composes direct and derived pair histories from native series', async () => {
    const out = await getFxFixSeries(['EUR/USD', 'EUR/JPY', 'BTC/USD'], 5000);
    expect(out['EUR/USD']).toEqual([
      { date: '2026-06-16', fix: 1.1 },
      { date: '2026-06-17', fix: 1.2 },
    ]);
    expect(out['EUR/JPY'][0].fix).toBeCloseTo(165, 10);
    // Outside the pair universe → anchors-only fallback upstream.
    expect(out['BTC/USD']).toEqual([]);
  });

  it('returns empty series when the table has no coverage', async () => {
    macroDb.rows = [];
    const out = await getFxFixSeries(['EUR/USD'], 5000);
    expect(out['EUR/USD']).toEqual([]);
  });
});

/* ------------------------------------------------------------------ *
 * DIG-320 (DIG-57 leaf 3) — one generation per (run_date, currency)
 *
 * Fixture provenance: `fx_consensus_snapshot` read from production on
 * 2026-10-04. A rerun of a run_date publishes a WHOLE second generation
 * beside the first, so most (run_date, currency) keys come back duplicated.
 * `run_date` 2026-06-02 holds three generations:
 *   2026-06-17 14:47:45.587511+00  19 rows / 10 currencies
 *   2026-06-30 23:00:54.339621+00   5 rows /  5 currencies  (partial rerun)
 *   2026-07-23 22:43:39.052539+00 23 rows / 10 currencies
 * The stamps keep their 6 fractional-second digits, which is what the
 * database returns. The middle generation is PARTIAL, so resolving by
 * generation would delete the five currencies only it republished; the
 * guard keys on (run_date, currency) instead. Which currencies and
 * row counts go with each generation are a fixture choice — the stamp
 * instants and the duplicated-key shape are not.
 * ------------------------------------------------------------------ */

const G_OLDEST = '2026-06-17 14:47:45.587511+00';
const G_PARTIAL = '2026-06-30 23:00:54.339621+00';
const G_NEWEST = '2026-07-23 22:43:39.052539+00';

const CURRENCIES = [
  'USD',
  'EUR',
  'JPY',
  'GBP',
  'CHF',
  'CAD',
  'AUD',
  'NZD',
  'SEK',
  'NOK',
] as const;
const PARTIAL_CURRENCIES = ['USD', 'EUR', 'JPY', 'GBP', 'CHF'] as const;

/** A weighted medium-horizon consensus row; only the dedupe and delta legs carry meaning. */
function consensusRow(
  run_date: string,
  currency: string,
  as_of: string,
  overrides: Partial<FxConsensusSnapshotRow> = {}
): FxConsensusSnapshotRow {
  return {
    run_date,
    currency,
    timeframe: 'medium',
    horizon_weeks: 4,
    weighted: true,
    score: 0,
    confidence: 0.5,
    agreement: 0.5,
    tilt: 0,
    n_eff: 1,
    n_brokers: 1,
    n_views: 1,
    bullish_pct: 0.25,
    bearish_pct: 0.25,
    neutral_pct: 0.25,
    watch_pct: 0.25,
    as_of,
    ...overrides,
  };
}

function generation(
  run_date: string,
  as_of: string,
  currencies: readonly string[],
  scoreBase: number
): FxConsensusSnapshotRow[] {
  return currencies.map((currency, i) =>
    consensusRow(run_date, currency, as_of, {
      score: scoreBase + i / 10,
      confidence: 0.4 + i / 100,
    })
  );
}

/** The production 2026-06-02 shape: three generations, the middle one partial. */
function threeGenerations(run_date = '2026-06-02'): FxConsensusSnapshotRow[] {
  return [
    ...generation(run_date, G_OLDEST, CURRENCIES, 1),
    ...generation(run_date, G_PARTIAL, PARTIAL_CURRENCIES, 2),
    ...generation(run_date, G_NEWEST, CURRENCIES, 3),
  ];
}

/**
 * Production duplication across the whole read: 2026-06-01..2026-06-05 and
 * 2026-06-08 each carry two whole generations, so 9-10 of their keys are
 * duplicated. 2026-06-01 drops one currency, the rest carry all ten.
 */
const DUPLICATED_DATES = [
  '2026-06-01',
  '2026-06-02',
  '2026-06-03',
  '2026-06-04',
  '2026-06-05',
  '2026-06-08',
] as const;

function duplicatedGenerations(): FxConsensusSnapshotRow[] {
  return DUPLICATED_DATES.flatMap((run_date, d) => {
    const currencies = d === 0 ? CURRENCIES.slice(0, 9) : CURRENCIES;
    // Two whole generations per date, 90 minutes apart, oldest first.
    return [
      ...generation(run_date, `${run_date}T22:00:00.000000+00:00`, currencies, 1),
      ...generation(run_date, `${run_date}T23:30:00.000000+00:00`, currencies, 3),
    ];
  });
}

describe('getConsensusTimeSeries generation dedupe', () => {
  beforeEach(() => {
    consensusDb.rows = [];
    consensusDb.queries = [];
  });

  afterEach(() => {
    consensusDb.rows = [];
    consensusDb.queries = [];
  });

  // DIG-57 spec acceptance test 12.
  it('returns at most one row per run_date + currency', async () => {
    consensusDb.rows = duplicatedGenerations();

    const out = await getConsensusTimeSeries('medium');

    const keys = out.map((r) => `${r.run_date}|${r.currency}`);
    expect(keys).toHaveLength(new Set(keys).size);
    // 9 currencies on 2026-06-01, ten on each of the other five dates.
    expect(out).toHaveLength(9 + 10 * (DUPLICATED_DATES.length - 1));
  });

  it('keeps the newest generation and keeps the series oldest→newest', async () => {
    consensusDb.rows = duplicatedGenerations();

    const out = await getConsensusTimeSeries('medium');

    for (const row of out) {
      expect(row.as_of).toBe(`${row.run_date}T23:30:00.000000+00:00`);
    }
    // `computeConsensusDeltaSet` walks the array from the end to find the newest
    // run_date, so the dedupe must not reorder what the query ordered.
    const dates = out.map((r) => r.run_date);
    expect(dates).toEqual([...dates].sort());
  });

  it('keeps a currency that only a stale generation published', async () => {
    // The newest generation dropped CHF; only the partial middle generation
    // republished it. Resolving per generation would delete CHF outright.
    consensusDb.rows = [
      ...generation('2026-06-02', G_OLDEST, CURRENCIES, 1),
      ...generation('2026-06-02', G_PARTIAL, PARTIAL_CURRENCIES, 2),
      ...generation('2026-06-02', G_NEWEST, CURRENCIES.filter((c) => c !== 'CHF'), 3),
    ];

    const out = await getConsensusTimeSeries('medium');

    const byCcy = new Map(out.map((r) => [r.currency, r.as_of]));
    expect([...byCcy.keys()].sort()).toEqual([...CURRENCIES].sort());
    expect(byCcy.get('CHF')).toBe(G_PARTIAL);
    expect(byCcy.get('USD')).toBe(G_NEWEST);
  });

  it('applies the dedupe client-side in a single query', async () => {
    consensusDb.rows = duplicatedGenerations();

    await getConsensusTimeSeries('medium');

    expect(consensusDb.queries).toHaveLength(1);
    expect(consensusDb.queries[0].eq).toEqual([
      ['weighted', true],
      ['timeframe', 'medium'],
    ]);
  });

  it('ignores rows outside the requested timeframe or weight', async () => {
    consensusDb.rows = [
      ...threeGenerations(),
      consensusRow('2026-06-02', 'USD', G_NEWEST, { timeframe: 'long' }),
      consensusRow('2026-06-02', 'EUR', G_NEWEST, { weighted: false }),
    ];

    const out = await getConsensusTimeSeries('medium');

    expect(out).toHaveLength(CURRENCIES.length);
    expect(out.every((r) => r.timeframe === 'medium' && r.weighted)).toBe(true);
  });
});

describe('computeConsensusDeltaSet generation dedupe', () => {
  // DIG-57 spec acceptance test 11. The function is exported and pure, so it is
  // handed raw rows here — the defensive pass must not depend on the read.
  it('returns one movers entry per currency over two generations of one date', () => {
    const series = [
      // Previous run_date: one generation.
      ...generation('2026-06-01', G_OLDEST, CURRENCIES, 0),
      // Newest run_date: two generations of the same date, older first.
      ...generation('2026-06-02', G_OLDEST, CURRENCIES, 1),
      ...generation('2026-06-02', G_NEWEST, CURRENCIES, 3),
    ];

    const deltas = computeConsensusDeltaSet(series);

    expect(deltas.runDate).toBe('2026-06-02');
    expect(deltas.prevRunDate).toBe('2026-06-01');
    expect(deltas.byCurrency).toHaveProperty('USD');
    expect(deltas.byCurrency.USD.scoreNow).toBe(
      series.find((r) => r.run_date === '2026-06-02' && r.currency === 'USD' && r.as_of === G_NEWEST)
        ?.score
    );
    // `byCurrency` is keyed per currency; `movers` is the capped top-6, so uniqueness
    // is the invariant here, not coverage.
    expect(Object.keys(deltas.byCurrency).sort()).toEqual([...CURRENCIES].sort());
    const currencies = deltas.movers.map((m) => m.currency);
    expect(currencies).toHaveLength(new Set(currencies).size);
    expect(currencies.length).toBeLessThanOrEqual(6);
    expect(currencies.every((c) => (CURRENCIES as readonly string[]).includes(c))).toBe(true);
  });

  it('scores the delta against the newest generation, not whichever arrived last', () => {
    const series = [
      consensusRow('2026-06-01', 'USD', G_OLDEST, { score: 0.2, confidence: 0.5 }),
      // A stale generation that arrived last and would win a last-write-wins loop.
      consensusRow('2026-06-02', 'USD', G_PARTIAL, { score: 0.8, confidence: 0.9 }),
      consensusRow('2026-06-02', 'USD', G_NEWEST, { score: -0.4, confidence: 0.3 }),
    ];

    const deltas = computeConsensusDeltaSet(series);

    expect(deltas.byCurrency.USD.scoreNow).toBe(-0.4);
    expect(deltas.byCurrency.USD.scorePrev).toBe(0.2);
    expect(deltas.byCurrency.USD.scoreDelta).toBeCloseTo(-0.6, 10);
    expect(deltas.byCurrency.USD.confidenceDelta).toBeCloseTo(-0.2, 10);
    expect(deltas.byCurrency.USD.flippedDirection).toBe(true);
    expect(deltas.movers).toHaveLength(1);
    expect(deltas.movers[0]).toEqual({
      currency: 'USD',
      scoreNow: -0.4,
      scoreDelta: deltas.byCurrency.USD.scoreDelta,
      absDelta: Math.abs(deltas.byCurrency.USD.scoreDelta ?? 0),
      direction: 'down',
    });
  });

  it('does not mutate the caller series', () => {
    const series = threeGenerations();
    const snapshot = series.map((r) => `${r.run_date}|${r.currency}|${r.as_of}`);

    computeConsensusDeltaSet(series);

    expect(series.map((r) => `${r.run_date}|${r.currency}|${r.as_of}`)).toEqual(snapshot);
  });

  it('still returns the empty set for an empty series', () => {
    expect(computeConsensusDeltaSet([])).toEqual({
      runDate: null,
      prevRunDate: null,
      byCurrency: {},
      movers: [],
    });
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
      // Distinct event_name from id 7: #4739's twin dedup collapses rows sharing one
      // join key, which would drop this row before the horizon rule could be tested.
      ev({ id: 8, event_date: '2026-08-15', event_datetime_utc: '2026-08-15T12:30:00Z', event_name: 'UoM Consumer Sentiment' }),
    ];
    expect((await getUpcomingEvents()).map((e) => e.id)).toEqual([7]);
  });

  it('holds for an eastern viewer whose local day runs ahead of UTC', async () => {
    // 12:30 Aug 1 in Auckland = 00:30 Aug 1 UTC. The 23:00Z Jul 31 release is already
    // Aug 1 locally, so it belongs to this viewer's today; the 09:00Z one is Jul 31.
    useViewer('Pacific/Auckland', '2026-08-01T00:30:00Z');
    calendarDb.rows = [
      ev({ id: 9, event_date: '2026-07-31', event_datetime_utc: '2026-07-31T23:00:00Z' }),
      // Distinct event_name from id 9 so the pair is not collapsed as twins by #4739's
      // dedup — this test must still exercise the local-date keying itself.
      ev({ id: 10, event_date: '2026-07-31', event_datetime_utc: '2026-07-31T09:00:00Z', event_name: 'Retail Sales' }),
    ];
    expect((await getTodayEvents()).map((e) => e.id)).toEqual([9]);
    expect((await getUpcomingEvents()).map((e) => e.id)).toEqual([9]);
  });

  it('#4739: collapses forexfactory/gloomberb twins of one logical event to a single row', async () => {
    // Both rows are ONE logical event ingested twice: identical (event_date, country,
    // event_name), but event_time is ET vs UTC (+4h) and the external_id prefix
    // differs — the shape that made EventsTab render two identical rows per event.
    useViewer('America/New_York', '2026-08-01T01:30:00Z');
    calendarDb.rows = [
      ev({ id: 1, external_id: 'te-918844', event_date: '2026-07-31', event_time: '8:30am', event_datetime_utc: '2026-07-31T12:30:00Z', event_name: 'Nonfarm Payrolls' }),
      ev({ id: 2, external_id: 'gb-20260731-nfp', event_date: '2026-07-31', event_time: '12:30', event_datetime_utc: '2026-07-31T12:30:04Z', event_name: 'Nonfarm Payrolls' }),
    ];
    expect((await getUpcomingEvents()).map((e) => e.id)).toHaveLength(1);
  });

  it('#4739: prefers the gloomberb twin whenever it is present, in either position', async () => {
    useViewer('America/New_York', '2026-08-01T01:30:00Z');
    const ff = ev({ id: 1, external_id: 'te-918844', event_date: '2026-07-31', event_name: 'Nonfarm Payrolls' });
    const gb = ev({ id: 2, external_id: 'gb-20260731-nfp', event_date: '2026-07-31', event_name: 'Nonfarm Payrolls' });
    // gb second: it must displace the incumbent ff row…
    calendarDb.rows = [ff, gb];
    expect((await getUpcomingEvents()).map((e) => e.external_id)).toEqual(['gb-20260731-nfp']);
    // …and gb first: a later ff row must NOT take the slot back.
    calendarDb.rows = [gb, ff];
    expect((await getUpcomingEvents()).map((e) => e.external_id)).toEqual(['gb-20260731-nfp']);
  });

  it('#4739: leaves rows with distinct names or dates untouched', async () => {
    useViewer('America/New_York', '2026-08-01T01:30:00Z');
    calendarDb.rows = [
      // Same day, different name…
      ev({ id: 1, external_id: 'gb-nfp', event_date: '2026-07-31', event_name: 'Nonfarm Payrolls' }),
      ev({ id: 2, external_id: 'gb-cpi', event_date: '2026-07-31', event_name: 'CPI m/m' }),
      // …and the same name on a different day. Neither pair shares a join key.
      ev({ id: 3, external_id: 'te-nfp', event_date: '2026-08-05', event_name: 'Nonfarm Payrolls' }),
    ];
    expect((await getUpcomingEvents()).map((e) => e.id)).toEqual([1, 2, 3]);
  });

  it('#4739: the winning twin keeps its original position in the query order', async () => {
    useViewer('America/New_York', '2026-08-01T01:30:00Z');
    calendarDb.rows = [
      ev({ id: 1, external_id: 'gb-cpi', event_date: '2026-07-31', event_datetime_utc: '2026-07-31T13:30:00Z', event_name: 'CPI m/m' }),
      // Twin pair for ONE event — id 2 (ff) is dropped, id 3 (gb) wins…
      ev({ id: 2, external_id: 'te-918844', event_date: '2026-07-31', event_datetime_utc: '2026-07-31T12:30:00Z', event_name: 'Nonfarm Payrolls' }),
      ev({ id: 3, external_id: 'gb-20260731-nfp', event_date: '2026-07-31', event_datetime_utc: '2026-07-31T12:30:04Z', event_name: 'Nonfarm Payrolls' }),
      ev({ id: 4, external_id: 'gb-fomc', event_date: '2026-08-05', event_datetime_utc: '2026-08-05T18:00:00Z', event_name: 'FOMC Minutes' }),
    ];
    // …in place, between its original neighbours — not hoisted to the front nor dropped
    // to the end, so the query's event_datetime_utc ordering downstream is unchanged.
    expect((await getUpcomingEvents()).map((e) => e.id)).toEqual([1, 3, 4]);
  });
});
