/**
 * Slice 0008: allowlisted generic reads for the dashboard long tail.
 *
 * `GET /v1/tables/:table` proxies a read-only PostgREST SELECT to the house
 * Supabase project with the worker-held service-role key, so the static
 * dashboard bundle no longer needs any Supabase key in the browser. Only
 * allowlisted tables are served; house-scoped tables get the workspace pin
 * enforced server-side (the caller cannot widen it).
 *
 * No privilege widening pre-cutover: anon RLS is broadly `USING (true)`
 * (see `digiquant/supabase/migrations/001_initial_schema.sql:174-181`),
 * narrowed to house-only books and house+system documents by migration
 * `110_anon_house_only_private_books.sql`. Every row served here is already
 * readable with the public anon key: house tables carry the workspace pin
 * and `documents` carries the house+system pin, matching anon RLS exactly.
 *
 * Supported query language (exactly what the dashboard uses):
 *   select=col1,col2   order=col.asc|desc (repeatable)   limit=N (cap 5000)
 *   offset=N           eq.<col>=v  ilike.<col>=pat  like.<col>=pat
 *   in.<col>=a,b,c     lt.<col>=v  lte.<col>=v  gt.<col>=v  gte.<col>=v
 *
 * Unknown table → 404. Unknown operator / bad limit → 400. Missing worker
 * env → 502 `upstream_empty` (fail-closed, same shape as every other
 * route). There is no stub lane: generic reads have no fixtures.
 */

import { hasSupabaseEnv, supaGet, type SupabaseEnv } from './supabase';

export const HOUSE_WORKSPACE_ID = '6b753576-ced9-5319-9bfa-c5d0aacd9319';
/** System workspace (research library); anon RLS reads house OR system documents. */
export const SYSTEM_WORKSPACE_ID = '1105372f-4109-5815-be5a-21091ccfc8ad';

/** Tables the dashboard reads directly (mirrors `apps/dashboard/lib/*.ts`). */
const TABLE_ALLOWLIST = new Set([
  'daily_snapshots',
  'positions',
  'instruments',
  'theses',
  'portfolio_metrics',
  'documents',
  'position_events',
  'macro_series_observations',
  'decision_log',
  'run_health',
  'position_attribution',
  'run_event_trace',
  'public_daily_realized_attribution',
  'public_accounting_nav_history',
  // Slice 0008 rewire: dossier + observability reads (main-project tables, no house pin).
  'thesis_vehicles',
  'analyst_coverage',
]);

/** Tables that must always be scoped to the house workspace. */
const HOUSE_PINNED = new Set(['positions', 'position_events', 'portfolio_metrics']);
/**
 * Tables scoped to house OR system (anon RLS parity: migration
 * `110_anon_house_only_private_books.sql` reads house+system documents).
 */
const HOUSE_OR_SYSTEM_PINNED = new Set(['documents']);

const MAX_LIMIT = 5000;

const FILTER_OPS = new Set(['eq', 'ilike', 'like', 'in', 'lt', 'lte', 'gt', 'gte']);

type TablesErrorCode = 'bad_request' | 'not_found' | 'upstream_empty' | 'internal';

const ERROR_STATUS: Record<TablesErrorCode, number> = {
  bad_request: 400,
  not_found: 404,
  upstream_empty: 502,
  internal: 500,
};

function tablesError(
  code: TablesErrorCode,
  message: string,
  retrievalPin: string | null,
  details: Record<string, unknown> = {},
): Response {
  return Response.json(
    { error: { code, message, details, retrieval_pin: retrievalPin } },
    { status: ERROR_STATUS[code] },
  );
}

/** Thrown by `buildTableQuery` for 404/400 rejections; the handler maps it. */
export class TablesQueryError extends Error {
  constructor(
    readonly code: 'bad_request' | 'not_found',
    message: string,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

/** Build the PostgREST query string for an allowlisted table read. Pure. */
export function buildTableQuery(table: string, params: URLSearchParams): string {
  if (!TABLE_ALLOWLIST.has(table)) {
    throw new TablesQueryError('not_found', `table ${table} is not served by the dashboard API`, {
      table,
    });
  }
  const out = new URLSearchParams();
  const select = params.get('select');
  out.set('select', select && select.length > 0 ? select : '*');
  for (const [key, value] of params) {
    if (key === 'select' || key === 'order' || key === 'limit' || key === 'offset') continue;
    if (key === 'retrieval_pin') continue;
    const dot = key.indexOf('.');
    if (dot < 0) {
      throw new TablesQueryError('bad_request', `filter ${key} must be op.column`, { filter: key });
    }
    const op = key.slice(0, dot);
    const col = key.slice(dot + 1);
    if (!FILTER_OPS.has(op) || col.length === 0) {
      throw new TablesQueryError('bad_request', `unsupported filter ${key}`, { filter: key });
    }
    // PostgREST `in` takes a parenthesised list; callers pass CSV.
    out.append(col, op === 'in' ? `in.(${value})` : `${op}.${value}`);
  }
  if (HOUSE_PINNED.has(table)) {
    out.append('workspace_id', `eq.${HOUSE_WORKSPACE_ID}`);
  }
  if (HOUSE_OR_SYSTEM_PINNED.has(table)) {
    out.append('workspace_id', `in.(${HOUSE_WORKSPACE_ID},${SYSTEM_WORKSPACE_ID})`);
  }
  const orders = params.getAll('order');
  if (orders.length > 0) {
    for (const o of orders) {
      if (!/^[A-Za-z0-9_]+(\.(asc|desc))?$/.test(o)) {
        throw new TablesQueryError('bad_request', `bad order ${o}`, { order: o });
      }
    }
    out.set('order', orders.join(','));
  }
  const limitRaw = params.get('limit');
  if (limitRaw !== null) {
    const limit = Number(limitRaw);
    if (!Number.isInteger(limit) || limit < 1 || limit > MAX_LIMIT) {
      throw new TablesQueryError('bad_request', `limit must be an integer 1..${MAX_LIMIT}`, {
        limit: limitRaw,
      });
    }
    out.set('limit', String(limit));
  }
  const offsetRaw = params.get('offset');
  if (offsetRaw !== null) {
    const offset = Number(offsetRaw);
    if (!Number.isInteger(offset) || offset < 0) {
      throw new TablesQueryError('bad_request', 'offset must be an integer >= 0', {
        offset: offsetRaw,
      });
    }
    out.set('offset', String(offset));
  }
  return `${table}?${out.toString()}`;
}

/**
 * Ledger-idiom handler: returns null when the path is not a tables read so
 * the caller can fall through to the exact-match route table. Upstream
 * failures throw `UpstreamError`; the caller maps them to 502 via the
 * shared `failClosed` wrapper (same as every other route).
 */
export async function tryHandleTables(req: Request, env: SupabaseEnv): Promise<Response | null> {
  const url = new URL(req.url);
  const match = /^\/v1\/tables\/([A-Za-z0-9_]+)$/.exec(url.pathname);
  if (!match) return null;
  if (!hasSupabaseEnv(env)) {
    return tablesError(
      'upstream_empty',
      'dashboard API has no Supabase env configured',
      url.searchParams.get('retrieval_pin'),
      {},
    );
  }
  let query: string;
  try {
    query = buildTableQuery(match[1], url.searchParams);
  } catch (err) {
    if (err instanceof TablesQueryError) {
      return tablesError(err.code, err.message, url.searchParams.get('retrieval_pin'), err.details);
    }
    throw err;
  }
  const rows = (await supaGet(env, query)) as unknown[];
  return Response.json(rows);
}
