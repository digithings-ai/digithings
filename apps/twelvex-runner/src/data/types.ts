export type TableSpec = { pk: string[]; columns: string[] };

export type Filter = { column: string; op: "eq" | "gte" | "lte" | "gt" | "lt" | "in"; value: string | string[] };
export type Order = { column: string; desc: boolean };
export type SelectQuery = { table: string; columns: string[] | null; filters: Filter[]; order: Order[]; limit: number };
export type UpsertQuery = { table: string; rows: Record<string, unknown>[]; onConflict: string[] };

export interface Backend {
  readonly name: "supabase" | "d1";
  select(q: SelectQuery): Promise<Record<string, unknown>[]>;
  upsert(q: UpsertQuery): Promise<{ written: number }>;
}

/**
 * The data API's slice of the twelvex-runner env. The Supabase pair reuses the
 * runner's own twelve-x secrets, so the move adds no second copy of the key.
 */
export interface DataEnv {
  /** "supabase" (default until cutover) | "d1". */
  DATA_BACKEND?: string;
  /** Bearer required on every /v1 data call. Separate from RUNNER_AUTH_TOKEN. */
  DATA_API_TOKEN?: string;
  /** twelve-x's own D1 database (`twelvex`). Never a core database. */
  TWELVEX_DB?: D1Database;
  TWELVEX_SUPABASE_URL?: string;
  TWELVEX_SUPABASE_SERVICE_KEY?: string;
}
