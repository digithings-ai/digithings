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

export interface Env {
  DATA_BACKEND?: string;
  DATA_API_TOKEN?: string;
  TWELVEX_DB?: D1Database;
  SUPABASE_TWELVEX_URL?: string;
  SUPABASE_TWELVEX_SERVICE_KEY?: string;
}
