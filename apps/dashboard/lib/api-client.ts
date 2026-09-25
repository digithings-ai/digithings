/**
 * Slice 0008: typed client for the central dashboard API worker.
 *
 * All dashboard data pulls go through the Worker (`NEXT_PUBLIC_DASHBOARD_API_URL`)
 * instead of direct Supabase reads from the browser. Two route families:
 *
 * - Specific routes (`/portfolio`, `/brief`, `/performance`,
 *   `/kpis/live`, `/nav-series`, `/benchmarks`, `/ledger`) — use
 *   {@link apiGet}.
 * - Allowlisted generic reads (`GET /v1/tables/:table`, CONTRACT §7) for the
 *   long tail — use {@link apiTable} / {@link apiMaybeSingle}.
 *
 * Out of scope by design (separate backends, stay direct): twelve-x reads
 * (separate Supabase project + own session model), Supabase Realtime overlays
 * (`prices_live`, `postgres_changes`), Supabase Edge Functions
 * (billing/Alpaca/profile), and the digichat embed.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(status: number, code: string | null, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/** Base URL of the dashboard API worker, without a trailing slash. */
export function dashboardApiBase(): string {
  return (process.env.NEXT_PUBLIC_DASHBOARD_API_URL ?? '').replace(/\/+$/, '');
}

/** True when the dashboard API worker is configured. */
export function isApiConfigured(): boolean {
  return dashboardApiBase().length > 0;
}

function errorFromBody(status: number, body: unknown): ApiError {
  if (body !== null && typeof body === 'object' && !Array.isArray(body)) {
    const err = (body as Record<string, unknown>).error;
    if (err !== null && typeof err === 'object' && !Array.isArray(err)) {
      const rec = err as Record<string, unknown>;
      const code = typeof rec.code === 'string' ? rec.code : null;
      const message = typeof rec.message === 'string' ? rec.message : `request failed (${status})`;
      return new ApiError(status, code, message);
    }
  }
  return new ApiError(status, null, `request failed (${status})`);
}

/**
 * GET a specific worker route and parse the JSON body. Throws {@link ApiError}
 * on a non-2xx status.
 */
export async function apiGet<T>(path: string, query?: Record<string, string>): Promise<T> {
  const base = dashboardApiBase();
  if (base.length === 0) {
    throw new ApiError(0, 'not_configured', 'NEXT_PUBLIC_DASHBOARD_API_URL is not set');
  }
  const params = new URLSearchParams();
  if (query !== undefined) {
    for (const [key, value] of Object.entries(query)) params.set(key, value);
  }
  const qs = params.toString();
  const res = await fetch(qs.length > 0 ? `${base}${path}?${qs}` : `${base}${path}`);
  if (!res.ok) {
    throw errorFromBody(res.status, await res.json().catch(() => null));
  }
  return (await res.json()) as T;
}

export type TableOrder = { column: string; ascending?: boolean };

/**
 * Generic table read for `GET /v1/tables/:table` (CONTRACT §7). Filter keys
 * mirror the worker's `op.column` encoding exactly.
 */
export type TableRead = {
  select?: string;
  /** `col.asc` strings or `{ column, ascending }` objects (repeatable). */
  order?: Array<string | TableOrder> | string | TableOrder;
  limit?: number;
  offset?: number;
  eq?: Record<string, string | number>;
  ilike?: Record<string, string>;
  like?: Record<string, string>;
  in?: Record<string, Array<string | number>>;
  lt?: Record<string, string | number>;
  lte?: Record<string, string | number>;
  gt?: Record<string, string | number>;
  gte?: Record<string, string | number>;
  /** Echoed back as `retrieval_pin` (never used for access control). */
  retrievalPin?: string;
};

/** Encode a {@link TableRead} into the worker's `op.column` query language. */
export function encodeTableQuery(read: TableRead = {}): string {
  const params = new URLSearchParams();
  if (read.select !== undefined) params.set('select', read.select);
  const orders = read.order === undefined ? [] : Array.isArray(read.order) ? read.order : [read.order];
  for (const o of orders) {
    params.append('order', typeof o === 'string' ? o : `${o.column}.${o.ascending === false ? 'desc' : 'asc'}`);
  }
  if (read.limit !== undefined) params.set('limit', String(read.limit));
  if (read.offset !== undefined) params.set('offset', String(read.offset));
  const scalarOps: Array<[string, Record<string, string | number> | undefined]> = [
    ['eq', read.eq],
    ['ilike', read.ilike],
    ['like', read.like],
    ['lt', read.lt],
    ['lte', read.lte],
    ['gt', read.gt],
    ['gte', read.gte],
  ];
  for (const [op, map] of scalarOps) {
    if (map === undefined) continue;
    for (const [col, value] of Object.entries(map)) params.append(`${op}.${col}`, String(value));
  }
  if (read.in !== undefined) {
    for (const [col, values] of Object.entries(read.in)) {
      params.append(`in.${col}`, values.map(String).join(','));
    }
  }
  if (read.retrievalPin !== undefined) params.set('retrieval_pin', read.retrievalPin);
  return params.toString();
}

/** Read rows from an allowlisted table. Throws {@link ApiError} on failure. */
export async function apiTable<T>(table: string, read: TableRead = {}): Promise<T[]> {
  const base = dashboardApiBase();
  if (base.length === 0) {
    throw new ApiError(0, 'not_configured', 'NEXT_PUBLIC_DASHBOARD_API_URL is not set');
  }
  // NOTE: the query string is built directly (not via apiGet) because `order`
  // is repeatable and a Record would collapse repeated keys.
  const qs = encodeTableQuery(read);
  const res = await fetch(qs.length > 0 ? `${base}/v1/tables/${table}?${qs}` : `${base}/v1/tables/${table}`);
  if (!res.ok) {
    throw errorFromBody(res.status, await res.json().catch(() => null));
  }
  const rows = (await res.json()) as unknown;
  if (!Array.isArray(rows)) {
    throw new ApiError(200, 'bad_shape', `expected a row array from table ${table}`);
  }
  return rows as T[];
}

/** Read the first row of an allowlisted table, or null when it is empty. */
export async function apiMaybeSingle<T>(table: string, read: TableRead = {}): Promise<T | null> {
  const rows = await apiTable<T>(table, { ...read, limit: 1 });
  return rows.length > 0 ? rows[0] : null;
}
