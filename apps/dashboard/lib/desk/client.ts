/**
 * Desk reads for digiquant panes.
 *
 * {@link DigiCon} is the digiquant type for one read: dashboard-api envelope
 * fields (`data`, `as_of`, `retrieval_pin`, `provenance`). Market closes stay
 * on `lib/market-data.ts`. Allowlisted table rows use the same type with
 * provenance left null. Failures throw {@link ApiError}. Missing numbers stay null.
 */
import {
  ApiError,
  apiGet,
  apiTable,
  type TableRead,
} from '@/lib/api-client';
import type { ApiEnvelope, BriefApiData, PerformanceApiData, PortfolioApiData } from '@/lib/api-types';
import { DESK_ENDPOINTS, DESK_TABLES, type DeskTableName } from './paths';

export type DigiConProvenance = NonNullable<ApiEnvelope<unknown>['provenance']>;

/** One digiquant dashboard-api read. Not a package and not a route prefix. */
export interface DigiCon<T> {
  data: T;
  as_of: string | null;
  retrieval_pin: string | null;
  provenance: DigiConProvenance | null;
}

export interface DeskQuery {
  asOf?: string;
  retrievalPin?: string;
}

function queryParams(
  query: DeskQuery | undefined,
  extra?: Record<string, string>,
): Record<string, string> | undefined {
  const params: Record<string, string> = {};
  if (extra !== undefined) {
    for (const [key, value] of Object.entries(extra)) params[key] = value;
  }
  if (query?.asOf !== undefined) params.asOf = query.asOf;
  if (query?.retrievalPin !== undefined) params.retrieval_pin = query.retrievalPin;
  return Object.keys(params).length > 0 ? params : undefined;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function readProvenance(value: unknown): DigiConProvenance | null {
  const rec = asRecord(value);
  if (rec === null) return null;
  return {
    source: typeof rec.source === 'string' ? rec.source : '',
    tip_date: typeof rec.tip_date === 'string' ? rec.tip_date : null,
    contract: typeof rec.contract === 'string' ? rec.contract : null,
    seam: rec.seam === true,
    marks: typeof rec.marks === 'string' ? rec.marks : '',
  };
}

/** Parse a CONTRACT §1 envelope. Does not fill absent numbers with zero. */
export async function readEnvelope<T>(
  path: string,
  query?: Record<string, string>,
): Promise<DigiCon<T>> {
  const body = await apiGet<unknown>(path, query);
  const rec = asRecord(body);
  if (rec === null || !('data' in rec)) {
    throw new ApiError(200, 'bad_shape', `expected an envelope from ${path}`);
  }
  return {
    data: rec.data as T,
    as_of: typeof rec.as_of === 'string' || rec.as_of === null ? (rec.as_of as string | null) : null,
    retrieval_pin:
      typeof rec.retrieval_pin === 'string' || rec.retrieval_pin === null
        ? (rec.retrieval_pin as string | null)
        : null,
    provenance: readProvenance(rec.provenance),
  };
}

export function getPortfolio(query?: DeskQuery): Promise<DigiCon<PortfolioApiData>> {
  return readEnvelope(DESK_ENDPOINTS.portfolio, queryParams(query));
}

export interface AllocationRow {
  ticker: string;
  weight_pct: number | null;
  scaled_weight_pct: number | null;
  entry_price: number | null;
  current_price: number | null;
  unrealized_pct: number | null;
  marks: string | null;
  marks_as_of: string | null;
}

export interface AllocationsApiData {
  book_as_of: string | null;
  invested_pct: number | null;
  cash_pct: number | null;
  invested_definition: string;
  rows: AllocationRow[];
  marks_unstamped: boolean;
}

export function getAllocations(
  query?: DeskQuery & { includeMarks?: boolean },
): Promise<DigiCon<AllocationsApiData>> {
  const includeMarks = query?.includeMarks !== false;
  return readEnvelope(
    DESK_ENDPOINTS.allocations,
    queryParams(query, { include_marks: includeMarks ? 'true' : 'false' }),
  );
}

export function getBrief(
  query?: DeskQuery & { overlay?: 'auto' | 'off' },
): Promise<DigiCon<BriefApiData>> {
  return readEnvelope(
    DESK_ENDPOINTS.brief,
    queryParams(query, { overlay: query?.overlay ?? 'auto' }),
  );
}

export function getPerformance(
  query?: DeskQuery & { benchmark?: string; window?: 'inception' | '1y' | '6m' | '3m' },
): Promise<DigiCon<PerformanceApiData>> {
  return readEnvelope(
    DESK_ENDPOINTS.performance,
    queryParams(query, {
      benchmark: query?.benchmark ?? 'SPY',
      window: query?.window ?? 'inception',
    }),
  );
}

export interface NavSeriesPoint {
  index: number;
  date: string;
  nav: number | null;
  day_return_pct: number | null;
  contract: string | null;
}

export interface NavSeriesApiData {
  tip: { date: string | null; contract: string | null };
  points: NavSeriesPoint[];
}

export function getNavSeries(
  query?: Pick<DeskQuery, 'retrievalPin'> & { from?: string; to?: string },
): Promise<DigiCon<NavSeriesApiData>> {
  const extra: Record<string, string> = {};
  if (query?.from !== undefined) extra.from = query.from;
  if (query?.to !== undefined) extra.to = query.to;
  return readEnvelope(DESK_ENDPOINTS.navSeries, queryParams(query, extra));
}

/**
 * Live-marks snapshot only. The badge is always `live marks`.
 * CONTRACT §5 and §6.5: this read must never wear `finalized accounting`.
 */
export const KPIS_LIVE_BADGE = 'live marks' as const;

export interface KpisLiveApiData {
  quote_date: string | null;
  live_vs_mark_pct: number | null;
  day_return_live_pct: number | null;
  since_inception_live_pct: number | null;
  excess_live_pct: number | null;
  overlay_eligible: boolean;
  universe: string[];
}

export interface KpisLiveRead extends DigiCon<KpisLiveApiData> {
  badge: typeof KPIS_LIVE_BADGE;
}

export async function getKpisLive(query?: Pick<DeskQuery, 'retrievalPin'>): Promise<KpisLiveRead> {
  const read = await readEnvelope<KpisLiveApiData>(
    DESK_ENDPOINTS.kpisLive,
    queryParams(query),
  );
  return { ...read, badge: KPIS_LIVE_BADGE };
}

export interface BenchmarkPoint {
  date: string;
  close: number | null;
}

export interface BenchmarksApiData {
  universe: string[];
  series: Record<string, BenchmarkPoint[]>;
  aligned_start: string | null;
  overlap_days: number | null;
}

export function getBenchmarks(
  query?: Pick<DeskQuery, 'retrievalPin'> & { tickers?: string; from?: string; to?: string },
): Promise<DigiCon<BenchmarksApiData>> {
  const extra: Record<string, string> = {};
  if (query?.tickers !== undefined) extra.tickers = query.tickers;
  if (query?.from !== undefined) extra.from = query.from;
  if (query?.to !== undefined) extra.to = query.to;
  return readEnvelope(DESK_ENDPOINTS.benchmarks, queryParams(query, extra));
}

export type LedgerEventType = 'OPEN' | 'ADD' | 'EXIT' | 'TRIM';

export interface LedgerEvent {
  date: string;
  ticker: string;
  type: LedgerEventType | string;
  fill_price: number | null;
  avg_entry: number | null;
  realized_pct: number | null;
  prev_weight_pct: number | null;
  weight_pct: number | null;
}

export interface LedgerApiData {
  events: LedgerEvent[];
  next_cursor: string | null;
}

export function getLedger(
  query?: DeskQuery & { ticker?: string; limit?: number; cursor?: string },
): Promise<DigiCon<LedgerApiData>> {
  const extra: Record<string, string> = {};
  if (query?.ticker !== undefined) extra.ticker = query.ticker;
  if (query?.limit !== undefined) extra.limit = String(query.limit);
  if (query?.cursor !== undefined) extra.cursor = query.cursor;
  return readEnvelope(DESK_ENDPOINTS.ledger, queryParams(query, extra));
}

export function isDeskTable(table: string): table is DeskTableName {
  return (DESK_TABLES as readonly string[]).includes(table);
}

/**
 * Allowlisted `GET /v1/tables/:table`. The worker returns a bare row array
 * (no envelope), so provenance is null. A missing service-role key is a 502
 * {@link ApiError}, not an empty success.
 */
export async function getTable<T>(
  table: string,
  read: TableRead = {},
): Promise<DigiCon<T[]>> {
  if (!isDeskTable(table)) {
    throw new ApiError(404, 'not_found', `table ${table} is not on the dashboard allowlist`);
  }
  const rows = await apiTable<T>(table, read);
  return {
    data: rows,
    as_of: null,
    retrieval_pin: read.retrievalPin ?? null,
    provenance: null,
  };
}

/** Map a thrown client error onto the pane error state. Does not invent a zero. */
export function deskFailure(err: unknown): { state: 'error'; errorMessage: string } {
  if (err instanceof ApiError) {
    return { state: 'error', errorMessage: err.message };
  }
  if (err instanceof Error && err.message.length > 0) {
    return { state: 'error', errorMessage: err.message };
  }
  return { state: 'error', errorMessage: 'request failed' };
}
