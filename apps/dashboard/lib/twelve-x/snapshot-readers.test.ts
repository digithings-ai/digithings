import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  getConsensusDivergence,
  getEventOpinions,
  getIntelligence,
  getIntelligenceWhy,
  getTopConfluence,
} from './fetch';
import type {
  FxConfluenceSnapshotRow,
  FxConsensusSnapshotRow,
  FxEventSnapshotRow,
} from './types';

/**
 * DIG-57 leaf 4 — the five single-date readers of the generation-stamped
 * twelve-x snapshot tables.
 *
 * These tests live in their own file because `fetch.test.ts` is leaf 3's. They
 * exercise the READ level through `./fetch`'s public API only, so a regression
 * in the anchor/filter wiring fails here and not somewhere inside the helper.
 *
 * The mock below emulates PostgREST: `.eq()` filters, `.order()` sorts and
 * `.limit()` truncates SERVER-side. That is load-bearing. A mock that returned
 * every fixture row regardless of the query would let a reader that filters
 * nothing still pass "returns only the newer generation", because the assertion
 * would be about the fixture rather than about the reader.
 */

/** One entry per AWAITED read, in the order the module issued them. */
interface RecordedQuery {
  table: string;
  columns: string;
  eq: [string, unknown][];
  range: [string, 'gte' | 'lte', unknown][];
  order: [string, unknown][];
  limit: number | null;
}

const snapshotDb = vi.hoisted(() => ({
  /**
   * Row fixtures per table. A table with no fixture answers empty.
   * `unknown[]` rather than `Record<string, unknown>[]`: the row types are
   * interfaces with no index signature, so they are not assignable to a
   * `Record<string, unknown>` without a cast at each of the 15 fixture sites.
   */
  rows: {} as Record<string, unknown[]>,
  queries: [] as {
    table: string;
    columns: string;
    eq: [string, unknown][];
    range: [string, 'gte' | 'lte', unknown][];
    order: [string, unknown][];
    limit: number | null;
  }[],
}));

vi.mock('./supabase', () => {
  interface SnapshotBuilder {
    select: (columns: string) => SnapshotBuilder;
    eq: (column: string, value: unknown) => SnapshotBuilder;
    gte: (column: string, value: unknown) => SnapshotBuilder;
    lte: (column: string, value: unknown) => SnapshotBuilder;
    order: (column: string, options?: unknown) => SnapshotBuilder;
    limit: (count: number) => SnapshotBuilder;
    then: <T>(onFulfilled: (payload: { data: unknown[] | null; error: unknown }) => T) => Promise<T>;
  }

  const makeBuilder = (table: string): SnapshotBuilder => {
    const record: RecordedQuery = {
      table,
      columns: '',
      eq: [],
      range: [],
      order: [],
      limit: null,
    };
    const builder: SnapshotBuilder = {
      select: (columns) => {
        record.columns = columns;
        return builder;
      },
      eq: (column, value) => {
        record.eq.push([column, value]);
        return builder;
      },
      gte: (column, value) => {
        record.range.push([column, 'gte', value]);
        return builder;
      },
      lte: (column, value) => {
        record.range.push([column, 'lte', value]);
        return builder;
      },
      order: (column, options) => {
        record.order.push([column, options]);
        return builder;
      },
      limit: (count) => {
        record.limit = count;
        return builder;
      },
      then: (onFulfilled) => {
        snapshotDb.queries.push(record);
        let rows = (snapshotDb.rows[table] ?? []).map(
          (row) => row as Record<string, unknown>,
        );
        rows = rows.filter((row) =>
          record.eq.every(([column, value]) => row[column] === value),
        );
        rows = rows.filter((row) =>
          record.range.every(([column, op, value]) =>
            op === 'gte'
              ? String(row[column]) >= String(value)
              : String(row[column]) <= String(value),
          ),
        );
        // Every fixture stamp in this file carries the same `+00` offset, so a
        // lexicographic sort is the chronological sort PostgREST performs on
        // `timestamptz`. Stable via index tiebreak.
        const decorated = rows.map((row, i) => ({ row, i }));
        for (const [column, options] of record.order) {
          const ascending =
            typeof options === 'object' && options !== null
              ? (options as { ascending?: boolean }).ascending !== false
              : true;
          decorated.sort((a, b) => {
            const av = String(a.row[column]);
            const bv = String(b.row[column]);
            if (av === bv) return a.i - b.i;
            const cmp = av < bv ? -1 : 1;
            return ascending ? cmp : -cmp;
          });
        }
        rows = decorated.map((d) => d.row);
        if (record.limit !== null) rows = rows.slice(0, record.limit);
        return Promise.resolve(onFulfilled({ data: rows, error: null }));
      },
    };
    return builder;
  };

  return {
    isTwelveXConfigured: () => true,
    twelveXSupabase: {
      from: (table: string) => makeBuilder(table),
    },
  };
});

/** `fetch.ts` imports the main dashboard client at module load; never used here. */
vi.mock('../supabase', () => ({
  isSupabaseConfigured: () => true,
  supabase: { from: () => makeThrowawayBuilder() },
}));

function makeThrowawayBuilder() {
  const builder = {
    select: () => builder,
    eq: () => builder,
    order: () => builder,
    limit: () => builder,
    then: (onFulfilled: (p: unknown) => unknown) =>
      Promise.resolve(onFulfilled({ data: [], error: null })),
  };
  return builder;
}

/* ------------------------------------------------------------------ *
 * Fixtures — real production stamps, 6 fractional digits, +00 offset
 * ------------------------------------------------------------------ */

/** Newest generation on 2026-06-02. Verbatim from the CTO's frame. */
const NEW_STAMP = '2026-07-23T22:43:39.052539+00:00';
/** Superseded generation on the same date. Verbatim from the CTO's frame. */
const OLD_STAMP = '2026-06-30T23:00:54.339621+00:00';

const CONFLUENCE_DATE = '2026-06-02';

function confluenceRow(
  overrides: Partial<FxConfluenceSnapshotRow> & Pick<FxConfluenceSnapshotRow, 'rank' | 'currency' | 'direction' | 'title'>
): FxConfluenceSnapshotRow {
  return {
    run_date: CONFLUENCE_DATE,
    score: 0,
    components: null,
    brief_keys: null,
    as_of: NEW_STAMP,
    ...overrides,
  } as FxConfluenceSnapshotRow;
}

/** The CTO's regression frame, exactly as described on the issue. */
function ctoFrameRows(): FxConfluenceSnapshotRow[] {
  return [
    confluenceRow({
      rank: 1,
      currency: 'USD',
      direction: 'long',
      title: 'USD LONG — via USD',
      score: 1.4,
      as_of: NEW_STAMP,
    }),
    confluenceRow({
      rank: 2,
      currency: 'USD',
      direction: 'short',
      title: 'USD SHORT — via USD/KRW',
      score: 1.1,
      as_of: OLD_STAMP,
    }),
    confluenceRow({
      rank: 3,
      currency: 'NOK',
      direction: 'long',
      title: 'NOK LONG — via NOK/EUR',
      score: 0.8,
      as_of: OLD_STAMP,
    }),
  ];
}

function eventRow(
  overrides: Partial<FxEventSnapshotRow> &
    Pick<FxEventSnapshotRow, 'run_date' | 'event_key' | 'event_name' | 'mentions' | 'as_of'>
): FxEventSnapshotRow {
  return {
    event_date: overrides.run_date,
    calendar_external_id: `cal-${overrides.event_key}`,
    release_at: null,
    category: 'macro',
    currencies: [],
    brokers: [],
    citations: [],
    ...overrides,
  } as FxEventSnapshotRow;
}

function consensusRow(
  overrides: Partial<FxConsensusSnapshotRow> &
    Pick<FxConsensusSnapshotRow, 'run_date' | 'currency' | 'as_of'>
): FxConsensusSnapshotRow {
  return {
    timeframe: 'medium',
    horizon_weeks: 4,
    weighted: true,
    score: 0,
    confidence: 0.6,
    agreement: 0.5,
    tilt: 0,
    n_eff: 3,
    n_brokers: 3,
    n_views: 6,
    bullish_pct: 0.5,
    bearish_pct: 0.2,
    neutral_pct: 0.2,
    watch_pct: 0.1,
    ...overrides,
  } as FxConsensusSnapshotRow;
}

/** Queries against one table, in issue order. */
function queriesFor(table: string): RecordedQuery[] {
  return snapshotDb.queries.filter((q) => q.table === table);
}

/** The `.eq('as_of', …)` value a query recorded, or undefined when it filtered nothing. */
function asOfEq(query: RecordedQuery): unknown {
  return query.eq.find(([column]) => column === 'as_of')?.[1];
}

let warnSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  snapshotDb.rows = {};
  snapshotDb.queries = [];
  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  warnSpy.mockRestore();
});

describe('DIG-57 leaf 4 — anchor-then-filter on the limited readers', () => {
  // Spec acceptance test 6. The stale generation sits at the LOWEST ranks, so
  // unanchored it fills the limit and the newest generation is cut off entirely.
  // This is the property `limit` truncation breaks and the anchor restores.
  const limitFixture = () => [
    confluenceRow({ rank: 1, currency: 'USD', direction: 'short', title: 'stale rank 1', as_of: OLD_STAMP }),
    confluenceRow({ rank: 2, currency: 'GBP', direction: 'long', title: 'stale rank 2', as_of: OLD_STAMP }),
    confluenceRow({ rank: 3, currency: 'EUR', direction: 'long', title: 'stale rank 3', as_of: OLD_STAMP }),
    confluenceRow({ rank: 4, currency: 'USD', direction: 'long', title: 'new rank 4', as_of: NEW_STAMP }),
    confluenceRow({ rank: 5, currency: 'JPY', direction: 'long', title: 'new rank 5', as_of: NEW_STAMP }),
  ];

  it('issues the anchor query first and filters the main query on its stamp', async () => {
    snapshotDb.rows.fx_confluence_snapshot = limitFixture();

    await getTopConfluence(CONFLUENCE_DATE, 3);

    const queries = queriesFor('fx_confluence_snapshot');
    expect(queries).toHaveLength(2);

    // Query 0 is the anchor: newest as_of for this run_date, one row.
    expect(queries[0].columns).toBe('as_of');
    expect(queries[0].eq).toContainEqual(['run_date', CONFLUENCE_DATE]);
    expect(queries[0].order).toContainEqual(['as_of', { ascending: false }]);
    expect(queries[0].limit).toBe(1);

    // Query 1 is the main read, and it filters on the stamp the anchor returned.
    expect(queries[1].columns).toContain('rank');
    expect(asOfEq(queries[1])).toBe(NEW_STAMP);
  });

  it('does not let the limit be consumed by the stale generation', async () => {
    snapshotDb.rows.fx_confluence_snapshot = limitFixture();

    const rows = await getTopConfluence(CONFLUENCE_DATE, 3);

    // Unanchored this returns three stale rows and no new-generation row at all.
    expect(rows.map((r) => r.title)).toEqual(['new rank 4', 'new rank 5']);
    expect(rows.every((r) => r.as_of === NEW_STAMP)).toBe(true);
  });

  it('passes the anchor stamp through byte-identically, with no Date round trip', async () => {
    snapshotDb.rows.fx_confluence_snapshot = limitFixture();

    await getTopConfluence(CONFLUENCE_DATE, 3);

    const anchor = queriesFor('fx_confluence_snapshot')[0];
    const main = queriesFor('fx_confluence_snapshot')[1];
    // The anchor query only selects `as_of`, so the value it resolved is the
    // stamp the fixture carries — read back out of the main query's recorded eq.
    const recorded = asOfEq(main);
    expect(recorded).toBe(NEW_STAMP);
    // Falsifier for a broken test. Measured on this host's Node v26.10.0:
    // `Date.parse` ACCEPTS `+00:00` and REJECTS the bare `+00` form, and
    // `toISOString()` truncates 6 fractional-second digits to 3 — the stamp
    // below becomes `...39.052Z`. So a round trip is provably a different
    // string, and this assertion cannot be satisfied by one.
    expect(new Date(NEW_STAMP).toISOString()).toBe('2026-07-23T22:43:39.052Z');
    expect(new Date(NEW_STAMP).toISOString()).not.toBe(NEW_STAMP);
    expect(anchor.columns).toBe('as_of');
  });

  it('anchors getIntelligence, the reader from the incident frame', async () => {
    snapshotDb.rows.fx_confluence_snapshot = limitFixture();

    const rows = await getIntelligence(CONFLUENCE_DATE, 24);

    const queries = queriesFor('fx_confluence_snapshot');
    expect(queries).toHaveLength(2);
    expect(asOfEq(queries[1])).toBe(NEW_STAMP);
    expect(rows.every((r) => r.as_of === NEW_STAMP)).toBe(true);
  });
});

describe('DIG-57 leaf 4 — the CTO regression frame, 2026-06-02', () => {
  it('returns the USD long row and never the USD short row', async () => {
    snapshotDb.rows.fx_confluence_snapshot = ctoFrameRows();

    const rows = await getTopConfluence(CONFLUENCE_DATE, 6);

    expect(rows.map((r) => r.title)).toEqual(['USD LONG — via USD']);

    // One screen must not call the same currency both ways.
    const usd = rows.filter((r) => r.currency === 'USD');
    expect(usd).toHaveLength(1);
    expect(usd[0].direction).toBe('long');
    expect(rows.some((r) => r.title.includes('USD SHORT'))).toBe(false);
    expect(rows.some((r) => r.as_of === OLD_STAMP)).toBe(false);
  });

  it('drops the superseded generation from getIntelligence too', async () => {
    snapshotDb.rows.fx_confluence_snapshot = ctoFrameRows();

    const rows = await getIntelligence(CONFLUENCE_DATE, 24);

    expect(rows.map((r) => r.title)).toEqual(['USD LONG — via USD']);
    expect(rows.some((r) => r.as_of === OLD_STAMP)).toBe(false);
  });
});

describe('DIG-57 leaf 4 — getEventOpinions keeps one whole generation', () => {
  // Spec acceptance test 7. Two publishes of the same date both carried the
  // same two event_keys, so a per-key filter would leave a partial middle
  // generation behind. The guard must return exactly the newer generation.
  const eventsFixture = () => [
    eventRow({ run_date: CONFLUENCE_DATE, event_key: 'NFP', event_name: 'Non-Farm Payrolls', mentions: 40, as_of: NEW_STAMP }),
    eventRow({ run_date: CONFLUENCE_DATE, event_key: 'CPI', event_name: 'CPI', mentions: 30, as_of: NEW_STAMP }),
    eventRow({ run_date: CONFLUENCE_DATE, event_key: 'FOMC', event_name: 'FOMC', mentions: 20, as_of: NEW_STAMP }),
    eventRow({ run_date: CONFLUENCE_DATE, event_key: 'NFP', event_name: 'Non-Farm Payrolls', mentions: 12, as_of: OLD_STAMP }),
    eventRow({ run_date: CONFLUENCE_DATE, event_key: 'CPI', event_name: 'CPI', mentions: 9, as_of: OLD_STAMP }),
  ];

  it('returns only the newer generation, with no duplicate event_key', async () => {
    snapshotDb.rows.fx_events_snapshot = eventsFixture();

    const rows = await getEventOpinions(CONFLUENCE_DATE);

    const keys = rows.map((r) => r.event_key);
    expect(keys).toEqual(['NFP', 'CPI', 'FOMC']);
    expect(new Set(keys).size).toBe(keys.length);
    expect(rows.every((r) => r.as_of === NEW_STAMP)).toBe(true);
  });

  it('anchors the events read on the same shape as the other two', async () => {
    snapshotDb.rows.fx_events_snapshot = eventsFixture();

    await getEventOpinions(CONFLUENCE_DATE);

    const queries = queriesFor('fx_events_snapshot');
    expect(queries).toHaveLength(2);
    expect(queries[0].columns).toBe('as_of');
    expect(queries[0].limit).toBe(1);
    expect(asOfEq(queries[1])).toBe(NEW_STAMP);
  });
});

describe('DIG-57 leaf 4 — the permanent-surplus dates', () => {
  // 2026-07-16 carries two publishes 4.08 h apart and 2026-07-17 carries eight
  // rows spanning 01:57 to 13:02. Both dates have zero briefs, so _prune never
  // reaches them and the surplus rows are permanent. The guard has to exclude
  // them at render time; nothing repairs them.
  it('2026-07-16 — keeps only the 13:23 publish', async () => {
    snapshotDb.rows.fx_events_snapshot = [
      eventRow({
        run_date: '2026-07-16',
        event_key: 'RETAIL',
        event_name: 'Retail Sales',
        mentions: 8,
        as_of: '2026-07-16T09:19:07.998304+00:00',
      }),
      eventRow({
        run_date: '2026-07-16',
        event_key: 'RETAIL',
        event_name: 'Retail Sales',
        mentions: 5,
        as_of: '2026-07-16T09:19:07.998304+00:00',
      }),
      eventRow({
        run_date: '2026-07-16',
        event_key: 'RETAIL',
        event_name: 'Retail Sales',
        mentions: 11,
        as_of: '2026-07-16T13:23:45.54194+00:00',
      }),
      eventRow({
        run_date: '2026-07-16',
        event_key: 'GDP',
        event_name: 'GDP Advance',
        mentions: 7,
        as_of: '2026-07-16T13:23:45.54194+00:00',
      }),
    ];

    const rows = await getEventOpinions('2026-07-16');

    expect(rows.map((r) => r.as_of)).toEqual([
      '2026-07-16T13:23:45.54194+00:00',
      '2026-07-16T13:23:45.54194+00:00',
    ]);
    expect(rows.map((r) => r.event_key)).toEqual(['RETAIL', 'GDP']);
  });

  it('2026-07-17 — keeps only the 13:02 publish across eight rows', async () => {
    const stamps = [
      '2026-07-17T01:57:53.18852+00:00',
      '2026-07-17T01:57:53.18852+00:00',
      '2026-07-17T01:57:53.18852+00:00',
      '2026-07-17T09:31:04.700112+00:00',
      '2026-07-17T09:31:04.700112+00:00',
      '2026-07-17T13:02:17.171707+00:00',
      '2026-07-17T13:02:17.171707+00:00',
      '2026-07-17T13:02:17.171707+00:00',
    ];
    snapshotDb.rows.fx_events_snapshot = stamps.map((as_of, i) =>
      eventRow({
        run_date: '2026-07-17',
        event_key: `EVT-${i}`,
        event_name: `Event ${i}`,
        mentions: 30 - i,
        as_of,
      }),
    );

    const rows = await getEventOpinions('2026-07-17');

    expect(rows).toHaveLength(3);
    expect(rows.every((r) => r.as_of === '2026-07-17T13:02:17.171707+00:00')).toBe(true);
    // The 01:57 rows outrank the 13:02 rows on mentions, so an unanchored read
    // with no limit returns a blend of two publishes. The surviving three are
    // the 13:02 rows, ranked mentions-descending.
    expect(rows.map((r) => r.mentions)).toEqual([25, 24, 23]);
  });
});

describe('DIG-57 leaf 4 — no-anchor degradation is observable', () => {
  it('still runs the main query when the anchor query finds nothing', async () => {
    // A run_date with no rows at all: the anchor query returns [], so there is
    // no stamp to filter on. The reader must degrade to today's behaviour.
    snapshotDb.rows.fx_confluence_snapshot = [];

    const rows = await getTopConfluence('2026-01-01', 6);

    expect(rows).toEqual([]);
    const queries = queriesFor('fx_confluence_snapshot');
    expect(queries).toHaveLength(2);
    expect(asOfEq(queries[1])).toBeUndefined();
  });

  it('degrades to the unanchored result when the date carries rows but no usable stamp', async () => {
    const rows = [
      confluenceRow({ rank: 1, currency: 'USD', direction: 'long', title: 'unstamped rank 1', as_of: '' }),
      confluenceRow({ rank: 2, currency: 'GBP', direction: 'long', title: 'unstamped rank 2', as_of: '' }),
    ];
    snapshotDb.rows.fx_confluence_snapshot = rows;

    const result = await getTopConfluence(CONFLUENCE_DATE, 6);

    // Today's behaviour: both rows, unfiltered, rather than an empty board.
    expect(result.map((r) => r.title)).toEqual(['unstamped rank 1', 'unstamped rank 2']);
    expect(asOfEq(queriesFor('fx_confluence_snapshot')[1])).toBeUndefined();
  });

  it('warns on the fallback path, naming the table and run_date only', async () => {
    snapshotDb.rows.fx_confluence_snapshot = [];

    await getTopConfluence('2026-01-01', 6);

    expect(warnSpy).toHaveBeenCalledTimes(1);
    const message = String(warnSpy.mock.calls[0][0]);
    expect(message).toContain('fx_confluence_snapshot');
    expect(message).toContain('2026-01-01');
    // Table and date only — no score, no row content, nothing client-facing.
    expect(message).not.toContain('USD');
    expect(message).not.toContain('LONG');
    expect(message).not.toMatch(/\d\.\d/);
  });

  /**
   * CONTRACT, not a pin: this is green on the unfixed tree too, because nothing
   * warns when nothing has an anchor. It is the other half of the pair with
   * "warns on the fallback path" — it says the warn is tied to the fallback and
   * not to every read, which is what keeps the warning signal readable.
   */
  it('does not warn when an anchor resolved', async () => {
    snapshotDb.rows.fx_confluence_snapshot = ctoFrameRows();

    await getTopConfluence(CONFLUENCE_DATE, 6);

    expect(warnSpy).not.toHaveBeenCalled();
  });
});

describe('DIG-57 leaf 4 — the two unbounded consensus reads', () => {
  // These two carry no limit, so the client-side series guard is the whole
  // remedy: one query, newest generation per (run_date, currency).
  const consensusFixture = (runDate: string) => [
    consensusRow({ run_date: runDate, currency: 'USD', score: 1.2, as_of: NEW_STAMP }),
    consensusRow({ run_date: runDate, currency: 'GBP', score: 0.4, as_of: NEW_STAMP }),
    // Same generation, no limit: the stale USD row would win the map otherwise.
    consensusRow({ run_date: runDate, currency: 'USD', score: -1.5, as_of: OLD_STAMP }),
  ];

  it('getConsensusDivergence reads the consensus table once, unanchored', async () => {
    snapshotDb.rows.fx_consensus_snapshot = consensusFixture(CONFLUENCE_DATE);
    snapshotDb.rows.fx_smart_bias = [
      { currency: 'USD', overall_sentiment: 'bullish', week_first_date: CONFLUENCE_DATE },
      { currency: 'GBP', overall_sentiment: 'bullish', week_first_date: CONFLUENCE_DATE },
    ];
    snapshotDb.rows.fx_market_snapshots = [];

    const out = await getConsensusDivergence(CONFLUENCE_DATE);

    const queries = queriesFor('fx_consensus_snapshot');
    expect(queries).toHaveLength(1);
    expect(asOfEq(queries[0])).toBeUndefined();
    expect(warnSpy).not.toHaveBeenCalled();

    // One entry per currency, carrying the newest generation's numbers.
    expect(Object.keys(out).sort()).toEqual(['GBP', 'USD']);
    expect(out.USD.consensusAsOf).toBe(NEW_STAMP);
    expect(out.USD.consensusScore).toBe(1.2);
  });

  it('getIntelligenceWhy reads the consensus table once, unanchored', async () => {
    snapshotDb.rows.fx_consensus_snapshot = consensusFixture(CONFLUENCE_DATE);
    snapshotDb.rows.fx_confluence_snapshot = [
      confluenceRow({ rank: 1, currency: 'USD', direction: 'long', title: 'USD LONG — via USD' }),
    ];
    snapshotDb.rows.fx_relevance_ledger = [];

    const payload = await getIntelligenceWhy(CONFLUENCE_DATE, 24);

    const queries = queriesFor('fx_consensus_snapshot');
    expect(queries).toHaveLength(1);
    expect(asOfEq(queries[0])).toBeUndefined();

    expect(payload.runDate).toBe(CONFLUENCE_DATE);
    expect(payload.items).toHaveLength(1);
    expect(payload.items[0].consensus?.score).toBe(1.2);
  });
});