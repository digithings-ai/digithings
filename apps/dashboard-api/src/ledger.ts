/**
 * GET /ledger pure logic (dashboard-api slice 0005).
 *
 * Contract: apps/dashboard-api/CONTRACT.md §6.8 — paginated house-book
 * `position_events` stream. Fills/weight changes only, never derived from
 * weight diffs. Economics mirror `apps/dashboard/lib/position-event-economics.ts`
 * (parity port, not a fork — keep both in sync).
 *
 * Self-contained: no worker runtime imports, no secrets, no network.
 * Slice 0002 (worker scaffold) owns `src/index.ts` wiring; this module drops
 * in at merge via `LEDGER_ROUTE` + `tryHandleLedger` (the mount function).
 * Nothing here imports `index.ts` — the contract surface only. The book
 * reader is injected as a minimal structural `LedgerBook` (same shape as the
 * scaffold's rest client), so tests run on a fake and merge supplies the
 * service-role reader. Reconcile the duplicated envelope/provenance shapes
 * with `index.ts` helpers at merge.
 *
 * All digi product names stay lowercase.
 */

export const HOUSE_WORKSPACE_ID = '6b753576-ced9-5319-9bfa-c5d0aacd9319';

export const LEDGER_EVENT_TYPES = ['OPEN', 'ADD', 'EXIT', 'TRIM'] as const;
export type LedgerEventType = (typeof LEDGER_EVENT_TYPES)[number];

export const LEDGER_DEFAULT_LIMIT = 50;
export const LEDGER_MAX_LIMIT = 500;
export const LEDGER_MAX_RETRIEVAL_PIN = 128;

/** Raw `position_events` row (house-book read, before normalization). */
export type PositionEventRow = {
  id?: string | null;
  date: string;
  ticker: string;
  event: string;
  weight_pct: number | string | null;
  prev_weight_pct: number | string | null;
  price: number | string | null;
  thesis_id?: string | null;
  reason?: string | null;
};

/** Cost-basis mark from the committed book (`positions.entry_price`). */
export type EntryPriceMark = {
  date: string;
  ticker: string;
  entry_price: number | null | undefined;
};

/** Contract §6.8 event shape. */
export type LedgerEvent = {
  date: string;
  ticker: string;
  type: LedgerEventType;
  fill_price: number | null;
  avg_entry: number | null;
  realized_pct: number | null;
  prev_weight_pct: number | null;
  weight_pct: number | null;
};

export type LedgerProvenance = {
  source: string;
  tip_date: string | null;
  contract: 'finalized_accounting' | 'legacy_estimate' | null;
  seam: boolean;
  marks: 'stored' | 'market_api' | 'unavailable';
};

export type LedgerQuery = {
  asOf: string | null;
  retrievalPin: string | null;
  ticker: string | null;
  limit: number;
  offset: number;
};

export type LedgerError = {
  status: number;
  body: {
    error: {
      code: string;
      message: string;
      details: Record<string, unknown>;
      retrieval_pin: string | null;
    };
  };
};

// ---------------------------------------------------------------------------
// validation helpers
// ---------------------------------------------------------------------------

function isCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [y, m, d] = value.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return (
    dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d
  );
}

function num(value: number | string | null | undefined): number | null {
  if (value == null) return null;
  const out = Number(value);
  return Number.isNaN(out) ? null : out;
}

function finitePositive(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value) || value <= 0) return null;
  return value;
}

export function roundPct(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}

// ---------------------------------------------------------------------------
// cursor (opaque, offset-based)
// ---------------------------------------------------------------------------

// Web-standard base64url (btoa/atob + TextEncoder) — runs in workerd,
// node, and browsers. No node `Buffer` (unavailable in workers).

function bytesToBase64Url(bytes: Uint8Array): string {
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64UrlToBytes(cursor: string): Uint8Array | null {
  if (cursor.length === 0) return null;
  try {
    let b64 = cursor.replace(/-/g, '+').replace(/_/g, '/');
    while (b64.length % 4 !== 0) b64 += '=';
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  } catch {
    return null;
  }
}

export function encodeLedgerCursor(offset: number): string {
  return bytesToBase64Url(new TextEncoder().encode(JSON.stringify({ v: 1, offset })));
}

export function decodeLedgerCursor(cursor: string): number | null {
  try {
    const bytes = base64UrlToBytes(cursor);
    if (bytes == null) return null;
    const parsed = JSON.parse(new TextDecoder().decode(bytes)) as unknown;
    if (
      typeof parsed !== 'object' ||
      parsed === null ||
      (parsed as { v?: unknown }).v !== 1 ||
      !Number.isInteger((parsed as { offset?: unknown }).offset) ||
      ((parsed as { offset: number }).offset as number) < 0
    ) {
      return null;
    }
    return (parsed as { offset: number }).offset;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// query parsing (fail closed → bad_request per contract §2)
// ---------------------------------------------------------------------------

export type LedgerQueryInput = {
  asOf?: string | null;
  retrieval_pin?: string | null;
  ticker?: string | null;
  limit?: string | number | null;
  cursor?: string | null;
};

export function errorEnvelope(
  code: string,
  message: string,
  retrievalPin: string | null,
  status: number,
  details: Record<string, unknown> = {},
): LedgerError {
  return {
    status,
    body: { error: { code, message, details, retrieval_pin: retrievalPin } },
  };
}

/**
 * Parse + validate GET /ledger query params. Returns the query or a
 * `bad_request` LedgerError (never throws on caller input).
 */
export function parseLedgerQuery(
  input: LedgerQueryInput,
): { query: LedgerQuery } | { error: LedgerError } {
  const pinRaw = input.retrieval_pin ?? null;
  if (pinRaw != null && pinRaw.length > LEDGER_MAX_RETRIEVAL_PIN) {
    return {
      error: errorEnvelope(
        'bad_request',
        `retrieval_pin exceeds ${LEDGER_MAX_RETRIEVAL_PIN} chars`,
        null,
        400,
      ),
    };
  }
  const retrievalPin = pinRaw && pinRaw.length > 0 ? pinRaw : null;

  const bad = (message: string, details: Record<string, unknown> = {}) => ({
    error: errorEnvelope('bad_request', message, retrievalPin, 400, details),
  });

  if (input.asOf != null && input.asOf !== '' && !isCalendarDate(input.asOf)) {
    return bad('asOf must be a calendar date YYYY-MM-DD', { asOf: input.asOf });
  }
  const asOf = input.asOf && input.asOf !== '' ? input.asOf : null;

  const tickerRaw = (input.ticker ?? '').trim().toUpperCase();
  const ticker = tickerRaw.length > 0 ? tickerRaw : null;

  let limit = LEDGER_DEFAULT_LIMIT;
  if (input.limit != null && String(input.limit) !== '') {
    const parsed = Number(input.limit);
    if (!Number.isInteger(parsed) || parsed <= 0) {
      return bad('limit must be a positive integer', { limit: input.limit });
    }
    if (parsed > LEDGER_MAX_LIMIT) {
      return bad(`limit exceeds max ${LEDGER_MAX_LIMIT}`, { limit: input.limit });
    }
    limit = parsed;
  }

  let offset = 0;
  if (input.cursor != null && input.cursor !== '') {
    const decoded = decodeLedgerCursor(input.cursor);
    if (decoded == null) return bad('cursor is malformed', {});
    offset = decoded;
  }

  return { query: { asOf, retrievalPin, ticker, limit, offset } };
}

// ---------------------------------------------------------------------------
// economics (parity with apps/dashboard/lib/position-event-economics.ts)
// ---------------------------------------------------------------------------

/**
 * Average entry as of an event date: latest `entry_price` on or before that
 * date for the ticker. Sells do not change average cost.
 */
export function averageEntryAsOf(
  positions: readonly EntryPriceMark[],
  ticker: string,
  asOfDate: string,
): number | null {
  const key = ticker.toUpperCase();
  let best: EntryPriceMark | null = null;
  for (const row of positions) {
    if (row.ticker.toUpperCase() !== key) continue;
    if (row.date > asOfDate) continue;
    if (finitePositive(row.entry_price) == null) continue;
    if (best == null || row.date.localeCompare(best.date) > 0) best = row;
  }
  return finitePositive(best?.entry_price);
}

/** Weight sold on a TRIM/EXIT — fail closed without a usable weight delta. */
export function soldWeightPct(event: {
  event: string;
  weight_pct: number | null | undefined;
  prev_weight_pct: number | null | undefined;
}): number | null {
  const prev = event.prev_weight_pct;
  const residual = event.weight_pct;
  if (prev != null && Number.isFinite(prev) && residual != null && Number.isFinite(residual)) {
    const sold = (prev as number) - (residual as number);
    return Number.isFinite(sold) ? roundPct(sold) : null;
  }
  if (event.event === 'EXIT' && prev != null && Number.isFinite(prev)) {
    return roundPct(prev as number);
  }
  return null;
}

/** Realized % for sells vs average entry — fail closed without fill or basis. */
export function realizedReturnVsAverageEntry(
  exitPrice: number | null | undefined,
  averageEntry: number | null,
): number | null {
  const sell = finitePositive(exitPrice);
  const entry = finitePositive(averageEntry);
  if (sell == null || entry == null) return null;
  return roundPct((sell / entry - 1) * 100);
}

export type LedgerEconomics = {
  avgEntry: number | null;
  fillPrice: number | null;
  soldWeightPct: number | null;
  realizedPct: number | null;
};

/**
 * Compact economics for one ledger row. TRIM/EXIT compute realized vs average
 * entry when both exist. OPEN/ADD prefer the book basis as of the event date
 * (fail closed to fill when no mark exists) — never label fill as average
 * cost when the book already carries a basis.
 */
export function ledgerEventEconomics(
  event: {
    event: string;
    ticker: string;
    date: string;
    weight_pct: number | null;
    prev_weight_pct: number | null;
    price: number | null;
  },
  positions: readonly EntryPriceMark[],
): LedgerEconomics {
  const fillPrice = finitePositive(event.price);
  const isSell = event.event === 'TRIM' || event.event === 'EXIT';
  const avgEntry = averageEntryAsOf(positions, event.ticker, event.date);
  if (!isSell) {
    return { avgEntry: avgEntry ?? fillPrice, fillPrice, soldWeightPct: null, realizedPct: null };
  }
  return {
    avgEntry,
    fillPrice,
    soldWeightPct: soldWeightPct(event),
    realizedPct: realizedReturnVsAverageEntry(fillPrice, avgEntry),
  };
}

// ---------------------------------------------------------------------------
// row → contract event
// ---------------------------------------------------------------------------

function isLedgerType(value: string): value is LedgerEventType {
  return (LEDGER_EVENT_TYPES as readonly string[]).includes(value);
}

/**
 * Normalize one raw row into a contract event, or null when the row is not a
 * ledger fill (HOLD/unknown types carry no fill and are excluded).
 */
export function buildLedgerEvent(
  row: PositionEventRow,
  positions: readonly EntryPriceMark[],
): LedgerEvent | null {
  if (!isLedgerType(row.event)) return null;
  const weight = num(row.weight_pct);
  const rawPrev = num(row.prev_weight_pct);
  const prev = row.event === 'OPEN' && rawPrev == null && weight != null ? 0 : rawPrev;
  const price = num(row.price);
  const economics = ledgerEventEconomics(
    { event: row.event, ticker: row.ticker, date: row.date, weight_pct: weight, prev_weight_pct: prev, price },
    positions,
  );
  return {
    date: row.date,
    ticker: row.ticker,
    type: row.event,
    fill_price: economics.fillPrice,
    avg_entry: economics.avgEntry,
    realized_pct: economics.realizedPct,
    prev_weight_pct: prev,
    weight_pct: weight,
  };
}

// ---------------------------------------------------------------------------
// page builder (filter → sort → paginate → envelope)
// ---------------------------------------------------------------------------

export type LedgerPageInput = {
  rows: readonly PositionEventRow[];
  positions: readonly EntryPriceMark[];
  query: LedgerQuery;
  provenance: LedgerProvenance;
};

export type LedgerPage = {
  status: number;
  body: {
    data: { events: LedgerEvent[]; next_cursor: string | null };
    as_of: string | null;
    retrieval_pin: string | null;
    provenance: LedgerProvenance;
  };
};

/**
 * Build the GET /ledger success body. Empty range is success with `[]` plus
 * honest provenance — never an error (contract §2).
 */
export function buildLedgerPage(input: LedgerPageInput): LedgerPage {
  const { rows, positions, query, provenance } = input;
  const events: LedgerEvent[] = [];
  for (const row of rows) {
    if (query.ticker != null && row.ticker.toUpperCase() !== query.ticker) continue;
    if (query.asOf != null && row.date > query.asOf) continue;
    const event = buildLedgerEvent(row, positions);
    if (event == null) continue;
    events.push(event);
  }
  events.sort((a, b) => b.date.localeCompare(a.date) || a.ticker.localeCompare(b.ticker));

  const slice = events.slice(query.offset, query.offset + query.limit);
  const end = query.offset + slice.length;
  const nextCursor = end < events.length ? encodeLedgerCursor(end) : null;

  return {
    status: 200,
    body: {
      data: { events: slice, next_cursor: nextCursor },
      as_of: query.asOf,
      retrieval_pin: query.retrievalPin,
      provenance,
    },
  };
}

// ---------------------------------------------------------------------------
// mount function (merge-time wiring; no index.ts import)
// ---------------------------------------------------------------------------

export const LEDGER_ROUTE = '/ledger';

/** Page size / row cap mirror the dashboard client precedent (no new budgets). */
export const LEDGER_FETCH_PAGE = 2500;
export const LEDGER_FETCH_MAX = 80000;

/**
 * Minimal structural book reader — same shape as the scaffold rest client, so
 * merge passes it straight through. Never constructed here (no secrets).
 */
export type LedgerBook = {
  getJson(path: string): Promise<unknown>;
};

function ledgerEventPath(offset: number, query: LedgerQuery): string {
  let path =
    `position_events?select=id,date,ticker,event,weight_pct,prev_weight_pct,` +
    `price,thesis_id,reason&workspace_id=eq.${HOUSE_WORKSPACE_ID}` +
    `&order=date.desc&limit=${LEDGER_FETCH_PAGE}&offset=${offset}`;
  if (query.asOf != null) path += `&date=lte.${query.asOf}`;
  if (query.ticker != null) path += `&ticker=eq.${query.ticker}`;
  return path;
}

function ledgerMarksPath(offset: number, asOf: string | null): string {
  let path =
    `positions?select=date,ticker,entry_price` +
    `&workspace_id=eq.${HOUSE_WORKSPACE_ID}` +
    `&order=date.desc&limit=${LEDGER_FETCH_PAGE}&offset=${offset}`;
  if (asOf != null) path += `&date=lte.${asOf}`;
  return path;
}

async function pagedBookRead<T>(book: LedgerBook, buildPath: (offset: number) => string): Promise<T[]> {
  const out: T[] = [];
  let offset = 0;
  for (;;) {
    const page = (await book.getJson(buildPath(offset))) as T[];
    if (!Array.isArray(page) || page.length === 0) break;
    out.push(...page);
    offset += page.length;
    if (page.length < LEDGER_FETCH_PAGE || out.length >= LEDGER_FETCH_MAX) break;
  }
  return out.slice(0, LEDGER_FETCH_MAX);
}

/** House-book `position_events` rows for the query (paged, mirrors the client). */
export function fetchLedgerRows(book: LedgerBook, query: LedgerQuery): Promise<PositionEventRow[]> {
  return pagedBookRead<PositionEventRow>(book, (offset) => ledgerEventPath(offset, query));
}

/** Committed-book cost-basis marks (`positions.entry_price`) for the query. */
export function fetchLedgerEntryMarks(
  book: LedgerBook,
  asOf: string | null,
): Promise<EntryPriceMark[]> {
  return pagedBookRead<EntryPriceMark>(book, (offset) => ledgerMarksPath(offset, asOf));
}

function normalizeLedgerPath(pathname: string): string {
  if (pathname.length > 1 && pathname.endsWith('/')) return pathname.slice(0, -1);
  return pathname || '/';
}

function toResponse(page: LedgerPage): Response {
  return Response.json(page.body, { status: page.status });
}

function toErrorResponse(error: LedgerError): Response {
  return Response.json(error.body, { status: error.status });
}

/**
 * Mount function for GET /ledger. Returns null when the request is not this
 * route (the scaffold router keeps owning 404s/methods). Otherwise parses,
 * reads the house book, and returns the contract §6.8 response. Required
 * upstream reads fail closed with `upstream_empty` — never synthesized.
 */
export async function tryHandleLedger(request: Request, book: LedgerBook): Promise<Response | null> {
  const url = new URL(request.url);
  if (request.method !== 'GET' || normalizeLedgerPath(url.pathname) !== LEDGER_ROUTE) {
    return null;
  }
  const parsed = parseLedgerQuery({
    asOf: url.searchParams.get('asOf'),
    retrieval_pin: url.searchParams.get('retrieval_pin'),
    ticker: url.searchParams.get('ticker'),
    limit: url.searchParams.get('limit'),
    cursor: url.searchParams.get('cursor'),
  });
  if (!('query' in parsed)) return toErrorResponse(parsed.error);
  const { query } = parsed;

  let rows: PositionEventRow[];
  let marks: EntryPriceMark[];
  try {
    [rows, marks] = await Promise.all([
      fetchLedgerRows(book, query),
      fetchLedgerEntryMarks(book, query.asOf),
    ]);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return toErrorResponse(
      errorEnvelope('upstream_empty', `book upstream read failed: ${message}`, query.retrievalPin, 502),
    );
  }

  let tipDate: string | null = null;
  for (const row of rows) {
    if (typeof row.date === 'string' && (tipDate == null || row.date > tipDate)) tipDate = row.date;
  }
  return toResponse(
    buildLedgerPage({
      rows,
      positions: marks,
      query,
      provenance: {
        source: 'position_events+positions',
        tip_date: tipDate,
        contract: null,
        seam: false,
        marks: marks.length > 0 ? 'stored' : 'unavailable',
      },
    }),
  );
}
