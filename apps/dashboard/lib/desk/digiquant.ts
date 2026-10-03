/**
 * digiquant house reads for Brief.
 *
 * These getters call the dashboard-api routes that serve the digiquant book
 * (`GET /brief`, `GET /portfolio`, `GET /allocations`, allowlisted tables).
 * Price bars stay on digiquant `GET /bars` via `fetchVelaBars`.
 *
 * TODO(slice-b): Slice B owns this client. Replace the seam with that export.
 * Do not add a second reader. Brief imports `getBrief`, `getPortfolio`,
 * `getAllocations`, and `getTable`.
 *
 * Throws {@link ApiError} on failure. Never coerces a missing figure to 0.
 */
import { ApiError, apiGet, apiTable, type TableRead } from '@/lib/api-client';
import type { ApiEnvelope, BriefApiData, PortfolioApiData } from '@/lib/api-types';

export interface DigiquantRead<T> {
  data: T;
  asOf: string | null;
  retrievalPin: string | null;
  provenance: ApiEnvelope<T>['provenance'];
}

export interface AllocationRowData {
  ticker: string;
  weight_pct: number | null;
  scaled_weight_pct: number | null;
  entry_price: number | null;
  current_price: number | null;
  unrealized_pct: number | null;
  marks: string;
  marks_as_of: string | null;
}

/** `GET /allocations` data object (CONTRACT §6.2). */
export interface AllocationsData {
  book_as_of: string | null;
  invested_pct: number | null;
  cash_pct: number | null;
  invested_definition: string;
  rows: AllocationRowData[];
  marks_unstamped: boolean;
}

/** Allowlisted `theses` columns Brief reads. Extra columns are ignored. */
export interface ThesisTableRow {
  thesis_id?: string;
  date?: string;
  name?: string | null;
  status?: string | null;
  notes?: string | null;
  invalidation?: string | null;
  invalidation_criteria?: unknown;
}

/** Allowlisted `run_health` columns Brief reads. */
export interface RunHealthRow {
  run_id?: string;
  run_date?: string | null;
  run_type?: string | null;
  status?: string | null;
  segments_total?: number | null;
  segments_ok?: number | null;
  segments_carried?: number | null;
  segments_failed?: number | null;
  created_at?: string | null;
  finished_at?: string | null;
  duration_s?: number | null;
}

export interface GetBriefOptions {
  overlay?: 'auto' | 'off';
  asOf?: string;
  retrievalPin?: string;
}

export interface GetRouteOptions {
  asOf?: string;
  retrievalPin?: string;
}

export interface GetAllocationsOptions extends GetRouteOptions {
  includeMarks?: boolean;
}

function queryOf(entries: Array<[string, string | undefined]>): Record<string, string> | undefined {
  const query: Record<string, string> = {};
  for (const [key, value] of entries) {
    if (value !== undefined) query[key] = value;
  }
  return Object.keys(query).length > 0 ? query : undefined;
}

function unwrap<T>(envelope: ApiEnvelope<T>, path: string): DigiquantRead<T> {
  if (envelope == null || typeof envelope !== 'object' || !('data' in envelope)) {
    throw new ApiError(200, 'bad_shape', `${path} envelope has no data`);
  }
  return {
    data: envelope.data,
    asOf: envelope.as_of ?? null,
    retrievalPin: envelope.retrieval_pin ?? null,
    provenance: envelope.provenance ?? null,
  };
}

/** `GET /brief`. Overlay defaults to the caller's choice; Brief passes `auto`. */
export async function getBrief(options: GetBriefOptions = {}): Promise<DigiquantRead<BriefApiData>> {
  const envelope = await apiGet<ApiEnvelope<BriefApiData>>(
    '/brief',
    queryOf([
      ['overlay', options.overlay],
      ['asOf', options.asOf],
      ['retrieval_pin', options.retrievalPin],
    ]),
  );
  return unwrap(envelope, '/brief');
}

/** `GET /portfolio`. CASH stays on the position list; callers drop it from name counts. */
export async function getPortfolio(
  options: GetRouteOptions = {},
): Promise<DigiquantRead<PortfolioApiData>> {
  const envelope = await apiGet<ApiEnvelope<PortfolioApiData>>(
    '/portfolio',
    queryOf([
      ['asOf', options.asOf],
      ['retrieval_pin', options.retrievalPin],
    ]),
  );
  return unwrap(envelope, '/portfolio');
}

/** `GET /allocations`. `includeMarks` maps to `include_marks` (default true). */
export async function getAllocations(
  options: GetAllocationsOptions = {},
): Promise<DigiquantRead<AllocationsData>> {
  const includeMarks = options.includeMarks !== false;
  const envelope = await apiGet<ApiEnvelope<AllocationsData>>(
    '/allocations',
    queryOf([
      ['include_marks', includeMarks ? 'true' : 'false'],
      ['asOf', options.asOf],
      ['retrieval_pin', options.retrievalPin],
    ]),
  );
  return unwrap(envelope, '/allocations');
}

/**
 * Allowlisted `GET /v1/tables/:table`. There is no `/movers` route and no
 * Gloomberg headline route — callers must not invent either here.
 */
export async function getTable<T>(table: string, read: TableRead = {}): Promise<T[]> {
  return apiTable<T>(table, read);
}
