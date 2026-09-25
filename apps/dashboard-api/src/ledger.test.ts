import { describe, expect, it } from 'vitest';
import {
  averageEntryAsOf,
  buildLedgerEvent,
  buildLedgerPage,
  decodeLedgerCursor,
  encodeLedgerCursor,
  HOUSE_WORKSPACE_ID,
  ledgerEventEconomics,
  parseLedgerQuery,
  realizedReturnVsAverageEntry,
  soldWeightPct,
  tryHandleLedger,
  type EntryPriceMark,
  type LedgerBook,
  type LedgerProvenance,
  type PositionEventRow,
} from './ledger';

const MARKS: EntryPriceMark[] = [
  { date: '2026-06-01', ticker: 'GLD', entry_price: 180 },
  { date: '2026-07-01', ticker: 'GLD', entry_price: 185 },
  { date: '2026-07-15', ticker: 'GLD', entry_price: 190 },
];

const PROVENANCE: LedgerProvenance = {
  source: 'house-book position_events',
  tip_date: '2026-09-03',
  contract: 'legacy_estimate',
  seam: false,
  marks: 'stored',
};

function row(partial: Partial<PositionEventRow> & { date: string; ticker: string }): PositionEventRow {
  return {
    event: 'TRIM',
    weight_pct: null,
    prev_weight_pct: null,
    price: null,
    ...partial,
  };
}

describe('averageEntryAsOf', () => {
  it('picks the latest entry on or before the event date', () => {
    expect(averageEntryAsOf(MARKS, 'GLD', '2026-06-15')).toBe(180);
    expect(averageEntryAsOf(MARKS, 'GLD', '2026-07-01')).toBe(185);
    expect(averageEntryAsOf(MARKS, 'gld', '2026-08-01')).toBe(190);
    expect(averageEntryAsOf(MARKS, 'GLD', '2026-05-01')).toBeNull();
    expect(averageEntryAsOf(MARKS, 'XLV', '2026-08-01')).toBeNull();
  });
});

describe('soldWeightPct', () => {
  it('computes sold weight as prev_weight − residual weight', () => {
    expect(soldWeightPct({ event: 'TRIM', prev_weight_pct: 9.9, weight_pct: 4.9 })).toBeCloseTo(
      5,
      5,
    );
    expect(soldWeightPct({ event: 'EXIT', prev_weight_pct: 8, weight_pct: 0 })).toBe(8);
  });

  it('falls back to prev alone on EXIT without a residual', () => {
    expect(soldWeightPct({ event: 'EXIT', prev_weight_pct: 8, weight_pct: null })).toBe(8);
  });

  it('fails closed without a usable weight delta', () => {
    expect(soldWeightPct({ event: 'TRIM', prev_weight_pct: null, weight_pct: 5 })).toBeNull();
    expect(
      soldWeightPct({ event: 'TRIM', prev_weight_pct: null, weight_pct: null }),
    ).toBeNull();
  });
});

describe('realizedReturnVsAverageEntry', () => {
  it('computes realized % vs average entry', () => {
    expect(realizedReturnVsAverageEntry(54.1, 52.0)).toBeCloseTo(4.038462, 5);
    expect(realizedReturnVsAverageEntry(110, 100)).toBeCloseTo(10, 5);
  });

  it('fails closed without fill price or cost basis', () => {
    expect(realizedReturnVsAverageEntry(null, 52.0)).toBeNull();
    expect(realizedReturnVsAverageEntry(54.1, null)).toBeNull();
    expect(realizedReturnVsAverageEntry(null, null)).toBeNull();
    expect(realizedReturnVsAverageEntry(0, 52.0)).toBeNull();
    expect(realizedReturnVsAverageEntry(54.1, 0)).toBeNull();
  });
});

describe('ledgerEventEconomics', () => {
  it('enriches the contract TRIM example (XLF @ 54.1 vs avg 52.0)', () => {
    const economics = ledgerEventEconomics(
      {
        event: 'TRIM',
        ticker: 'XLF',
        date: '2026-09-03',
        weight_pct: 4.9,
        prev_weight_pct: 9.9,
        price: 54.1,
      },
      [{ date: '2026-08-01', ticker: 'XLF', entry_price: 52.0 }],
    );
    expect(economics.fillPrice).toBe(54.1);
    expect(economics.avgEntry).toBe(52.0);
    expect(economics.soldWeightPct).toBeCloseTo(5, 5);
    expect(economics.realizedPct).toBeCloseTo((54.1 / 52.0 - 1) * 100, 5);
  });

  it('keeps realized null for OPEN/ADD and prefers the book basis', () => {
    const economics = ledgerEventEconomics(
      {
        event: 'ADD',
        ticker: 'GLD',
        date: '2026-07-15',
        weight_pct: 10,
        prev_weight_pct: 5,
        price: 250,
      },
      MARKS,
    );
    expect(economics.avgEntry).toBe(190);
    expect(economics.fillPrice).toBe(250);
    expect(economics.soldWeightPct).toBeNull();
    expect(economics.realizedPct).toBeNull();
  });

  it('fails closed on a sell without fill price or cost basis', () => {
    const noFill = ledgerEventEconomics(
      {
        event: 'EXIT',
        ticker: 'GLD',
        date: '2026-08-20',
        weight_pct: 0,
        prev_weight_pct: 8,
        price: null,
      },
      MARKS,
    );
    expect(noFill.realizedPct).toBeNull();
    expect(noFill.soldWeightPct).toBe(8);

    const noBasis = ledgerEventEconomics(
      {
        event: 'EXIT',
        ticker: 'NOPE',
        date: '2026-08-20',
        weight_pct: 0,
        prev_weight_pct: 8,
        price: 200,
      },
      MARKS,
    );
    expect(noBasis.avgEntry).toBeNull();
    expect(noBasis.realizedPct).toBeNull();
  });
});

describe('cursor round-trip', () => {
  it('encodes and decodes offsets losslessly', () => {
    for (const offset of [0, 50, 499]) {
      const cursor = encodeLedgerCursor(offset);
      expect(typeof cursor).toBe('string');
      expect(cursor).not.toContain('+');
      expect(cursor).not.toContain('/');
      expect(cursor).not.toContain('=');
      expect(decodeLedgerCursor(cursor)).toBe(offset);
    }
  });

  it('rejects malformed cursors', () => {
    expect(decodeLedgerCursor('!!!not-a-cursor!!!')).toBeNull();
    expect(decodeLedgerCursor('')).toBeNull();
    expect(decodeLedgerCursor(encodeLedgerCursor(10).slice(0, 4))).toBeNull();
  });
});

describe('parseLedgerQuery', () => {
  it('applies defaults (limit 50, offset 0)', () => {
    const parsed = parseLedgerQuery({});
    expect(parsed).toEqual({
      query: { asOf: null, retrievalPin: null, ticker: null, limit: 50, offset: 0 },
    });
  });

  it('accepts ticker/asOf/limit/cursor and echoes the pin', () => {
    const cursor = encodeLedgerCursor(50);
    const parsed = parseLedgerQuery({
      asOf: '2026-09-03',
      retrieval_pin: 'pin-123',
      ticker: 'xlf',
      limit: '25',
      cursor,
    });
    expect(parsed).toEqual({
      query: {
        asOf: '2026-09-03',
        retrievalPin: 'pin-123',
        ticker: 'XLF',
        limit: 25,
        offset: 50,
      },
    });
  });

  it('rejects malformed params with bad_request', () => {
    for (const input of [
      { limit: 'nope' },
      { limit: 0 },
      { limit: -5 },
      { limit: 501 },
      { limit: 2.5 },
      { asOf: '09/03/2026' },
      { asOf: '2026-13-01' },
      { cursor: 'broken' },
      { retrieval_pin: 'x'.repeat(129) },
    ]) {
      const parsed = parseLedgerQuery(input);
      expect('error' in parsed && parsed.error.body.error.code).toBe('bad_request');
      expect('error' in parsed && parsed.error.status).toBe(400);
    }
  });
});

describe('buildLedgerEvent', () => {
  it('maps a TRIM row to the contract shape', () => {
    const event = buildLedgerEvent(
      row({
        date: '2026-09-03',
        ticker: 'XLF',
        event: 'TRIM',
        weight_pct: 4.9,
        prev_weight_pct: 9.9,
        price: 54.1,
      }),
      [{ date: '2026-08-01', ticker: 'XLF', entry_price: 52.0 }],
    );
    expect(event).toMatchObject({
      date: '2026-09-03',
      ticker: 'XLF',
      type: 'TRIM',
      fill_price: 54.1,
      avg_entry: 52.0,
      prev_weight_pct: 9.9,
      weight_pct: 4.9,
    });
    expect(event?.realized_pct).toBeCloseTo((54.1 / 52.0 - 1) * 100, 5);
  });

  it('defaults OPEN prev weight to 0 when the book omits it', () => {
    const event = buildLedgerEvent(
      row({
        date: '2026-06-01',
        ticker: 'GLD',
        event: 'OPEN',
        weight_pct: 10,
        prev_weight_pct: null,
        price: 180,
      }),
      MARKS,
    );
    expect(event?.prev_weight_pct).toBe(0);
    expect(event?.realized_pct).toBeNull();
  });

  it('excludes HOLD rows (no fill in the ledger stream)', () => {
    expect(
      buildLedgerEvent(
        row({ date: '2026-08-01', ticker: 'GLD', event: 'HOLD', weight_pct: 5 }),
        MARKS,
      ),
    ).toBeNull();
  });
});

describe('buildLedgerPage', () => {
  const rows: PositionEventRow[] = [
    row({ date: '2026-09-03', ticker: 'XLF', event: 'TRIM', weight_pct: 4.9, prev_weight_pct: 9.9, price: 54.1 }),
    row({ date: '2026-08-20', ticker: 'GLD', event: 'TRIM', weight_pct: 5, prev_weight_pct: 10, price: 199.5 }),
    row({ date: '2026-08-01', ticker: 'HOLD', event: 'HOLD', weight_pct: 5 }),
    row({ date: '2026-06-01', ticker: 'GLD', event: 'OPEN', weight_pct: 10, prev_weight_pct: 0, price: 180 }),
  ];
  const marks: EntryPriceMark[] = [
    ...MARKS,
    { date: '2026-08-01', ticker: 'XLF', entry_price: 52.0 },
  ];

  function queryOf(input: Parameters<typeof parseLedgerQuery>[0]) {
    const parsed = parseLedgerQuery(input);
    if (!('query' in parsed)) throw new Error('expected valid query');
    return parsed.query;
  }

  it('sorts newest-first and drops non-fill rows', () => {
    const page = buildLedgerPage({
      rows,
      positions: marks,
      query: queryOf({}),
      provenance: PROVENANCE,
    });
    expect(page.status).toBe(200);
    expect(page.body.data.events.map((e) => e.date)).toEqual([
      '2026-09-03',
      '2026-08-20',
      '2026-06-01',
    ]);
    expect(page.body.data.next_cursor).toBeNull();
    expect(page.body.provenance).toEqual(PROVENANCE);
    expect(page.body.retrieval_pin).toBeNull();
  });

  it('paginates with opaque cursors across the full stream', () => {
    const first = buildLedgerPage({
      rows,
      positions: marks,
      query: queryOf({ limit: 2 }),
      provenance: PROVENANCE,
    });
    expect(first.body.data.events).toHaveLength(2);
    expect(first.body.data.next_cursor).not.toBeNull();

    const second = buildLedgerPage({
      rows,
      positions: marks,
      query: queryOf({ limit: 2, cursor: first.body.data.next_cursor }),
      provenance: PROVENANCE,
    });
    expect(second.body.data.events).toHaveLength(1);
    expect(second.body.data.next_cursor).toBeNull();
    expect(second.body.data.events[0]?.date).toBe('2026-06-01');
  });

  it('filters by ticker and asOf', () => {
    const page = buildLedgerPage({
      rows,
      positions: marks,
      query: queryOf({ ticker: 'gld', asOf: '2026-08-20' }),
      provenance: PROVENANCE,
    });
    expect(page.body.data.events.map((e) => e.ticker)).toEqual(['GLD', 'GLD']);
    expect(page.body.as_of).toBe('2026-08-20');
  });

  it('returns success with [] plus honest provenance on an empty range', () => {
    const page = buildLedgerPage({
      rows,
      positions: marks,
      query: queryOf({ ticker: 'NOPE' }),
      provenance: PROVENANCE,
    });
    expect(page.status).toBe(200);
    expect(page.body.data.events).toEqual([]);
    expect(page.body.data.next_cursor).toBeNull();
    expect(page.body.provenance).toEqual(PROVENANCE);
  });
});

describe('tryHandleLedger (mount function)', () => {
  const EVENTS: PositionEventRow[] = [
    { date: '2026-09-03', ticker: 'XLF', event: 'TRIM', weight_pct: 4.9, prev_weight_pct: 9.9, price: 54.1, thesis_id: null, reason: null },
    { date: '2026-08-20', ticker: 'GLD', event: 'TRIM', weight_pct: 5, prev_weight_pct: 10, price: 199.5, thesis_id: null, reason: null },
    { date: '2026-08-01', ticker: 'GLD', event: 'HOLD', weight_pct: 5, prev_weight_pct: 5, price: null, thesis_id: null, reason: null },
    { date: '2026-06-01', ticker: 'GLD', event: 'OPEN', weight_pct: 10, prev_weight_pct: 0, price: 180, thesis_id: null, reason: null },
  ];
  const MARKS = [
    { date: '2026-08-01', ticker: 'XLF', entry_price: 52.0 },
    { date: '2026-07-15', ticker: 'GLD', entry_price: 190 },
  ];

  /** In-memory fake of the scaffold rest client shape. */
  function fakeBook(): LedgerBook & { seen: string[] } {
    const seen: string[] = [];
    return {
      seen,
      async getJson(path: string): Promise<unknown> {
        seen.push(path);
        const [, query = ''] = path.split('?');
        const params = new URLSearchParams(query);
        if (!params.get('workspace_id')?.includes(HOUSE_WORKSPACE_ID)) {
          throw new Error('missing house workspace pin');
        }
        const table = path.split('?')[0];
        const source = table === 'position_events' ? EVENTS : MARKS;
        let rows = [...source];
        const lte = params.get('date')?.match(/^lte\.(.+)$/)?.[1];
        if (lte) rows = rows.filter((r) => (r as { date: string }).date <= (lte as string));
        const ticker = params.get('ticker')?.match(/^eq\.(.+)$/)?.[1];
        if (ticker) rows = rows.filter((r) => (r as { ticker: string }).ticker === ticker);
        const limit = Number(params.get('limit') ?? '1000');
        const offset = Number(params.get('offset') ?? '0');
        return rows.slice(offset, offset + limit);
      },
    };
  }

  function get(path: string): Request {
    return new Request(`https://dashboard-api.test${path}`, { method: 'GET' });
  }

  it('returns null for non-ledger routes and non-GET methods', async () => {
    const book = fakeBook();
    expect(await tryHandleLedger(get('/portfolio'), book)).toBeNull();
    expect(
      await tryHandleLedger(
        new Request('https://dashboard-api.test/ledger', { method: 'POST' }),
        book,
      ),
    ).toBeNull();
    expect(book.seen).toEqual([]);
  });

  it('serves the contract event stream with economics + provenance', async () => {
    const res = await tryHandleLedger(get('/ledger'), fakeBook());
    expect(res?.status).toBe(200);
    const body = (await res?.json()) as {
      data: { events: { ticker: string; type: string; realized_pct: number | null }[]; next_cursor: null };
      provenance: LedgerProvenance;
    };
    expect(body.data.events.map((e) => `${e.ticker}:${e.type}`)).toEqual([
      'XLF:TRIM',
      'GLD:TRIM',
      'GLD:OPEN',
    ]);
    expect(body.data.next_cursor).toBeNull();
    expect(body.provenance.source).toBe('position_events+positions');
    expect(body.provenance.tip_date).toBe('2026-09-03');
    expect(body.provenance.marks).toBe('stored');
    expect(body.data.events[0]?.realized_pct).toBeCloseTo((54.1 / 52.0 - 1) * 100, 5);
  });

  it('paginates through the mount and echoes the pin', async () => {
    const book = fakeBook();
    const first = await tryHandleLedger(get('/ledger?limit=2&retrieval_pin=pin-1'), book);
    const firstBody = (await first?.json()) as {
      data: { events: unknown[]; next_cursor: string };
      retrieval_pin: string;
    };
    expect(firstBody.data.events).toHaveLength(2);
    expect(firstBody.retrieval_pin).toBe('pin-1');

    const second = await tryHandleLedger(
      get(`/ledger?limit=2&cursor=${encodeURIComponent(firstBody.data.next_cursor)}`),
      book,
    );
    const secondBody = (await second?.json()) as {
      data: { events: unknown[]; next_cursor: null };
    };
    expect(secondBody.data.events).toHaveLength(1);
    expect(secondBody.data.next_cursor).toBeNull();
  });

  it('fails closed with the error envelope on bad params', async () => {
    const res = await tryHandleLedger(get('/ledger?limit=9999&retrieval_pin=pin-9'), fakeBook());
    expect(res?.status).toBe(400);
    const body = (await res?.json()) as {
      error: { code: string; retrieval_pin: string };
    };
    expect(body.error.code).toBe('bad_request');
    expect(body.error.retrieval_pin).toBe('pin-9');
  });

  it('returns upstream_empty when a required book read fails', async () => {
    const failing: LedgerBook = {
      async getJson(): Promise<unknown> {
        throw new Error('boom');
      },
    };
    const res = await tryHandleLedger(get('/ledger'), failing);
    expect(res?.status).toBe(502);
    const body = (await res?.json()) as { error: { code: string } };
    expect(body.error.code).toBe('upstream_empty');
  });
});
