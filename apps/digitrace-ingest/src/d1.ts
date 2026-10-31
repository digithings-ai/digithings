/**
 * D1 `digitrace`, the index's write path (DIG-2887 S1).
 *
 * Replaces the old sink into the core Postgres project. The schema is
 * `migrations/0001_digitrace_index.sql`; the columns are the ones
 * `index-rows.ts` builds, unchanged.
 *
 * Tenancy: D1 has no `workspaces` table, so the index's `workspace_id` column
 * holds the verified tenant slug. The receiver decided that slug from the
 * ingest token, and nothing here accepts a tenant from a queue payload beyond
 * the one `parseMessage` already bound to the archive key.
 *
 * Every write is one prepared statement per row, sent as one `batch()` (a D1
 * batch runs as a single transaction), with `ON CONFLICT ... DO UPDATE` on the
 * natural key: a retried queue message rewrites the same rows, as the
 * old `merge-duplicates` upsert did.
 */

export class D1ConfigError extends Error {
  constructor() {
    super("d1 is not configured: the INDEX_DB binding is missing");
    this.name = "D1ConfigError";
  }
}

export interface IndexDbEnv {
  INDEX_DB?: D1Database;
}

function db(env: IndexDbEnv): D1Database {
  if (!env.INDEX_DB) throw new D1ConfigError();
  return env.INDEX_DB;
}

/** The tables this consumer may write, with their natural keys. */
const WRITABLE: Record<string, readonly string[]> = {
  digitrace_traces: ["workspace_id", "trace_id"],
  digitrace_spans_index: ["workspace_id", "trace_id", "span_id"],
};

const IDENT = /^[a-z_][a-z0-9_]*$/;

/** A row value as D1 binds it: objects become JSON text, booleans 0/1. */
export function bindValue(value: unknown): string | number | null {
  if (value === undefined || value === null) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "bigint") return Number(value);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/** The upsert statement for one row shape. Exported for the tests. */
export function upsertSql(table: string, columns: string[], onConflict: string): string {
  const keys = WRITABLE[table];
  if (!keys) throw new Error(`d1: ${table} is not writable by the ingest consumer`);
  const conflict = onConflict.split(",").map((c) => c.trim());
  if (conflict.join(",") !== keys.join(",")) {
    throw new Error(`d1: ${table} conflict target must be ${keys.join(",")}`);
  }
  for (const column of columns) {
    if (!IDENT.test(column)) throw new Error(`d1: bad column name ${column}`);
  }
  const updates = columns.filter((c) => !keys.includes(c)).map((c) => `${c} = excluded.${c}`);
  const placeholders = columns.map((_, i) => `?${i + 1}`).join(", ");
  return (
    `INSERT INTO ${table} (${columns.join(", ")}) VALUES (${placeholders}) ` +
    `ON CONFLICT (${keys.join(", ")}) ` +
    (updates.length > 0 ? `DO UPDATE SET ${updates.join(", ")}` : "DO NOTHING")
  );
}

/** The tenancy key for a verified slug. Async to keep the consumer seam. */
export async function resolveWorkspaceId(_env: IndexDbEnv, slug: string): Promise<string> {
  return slug;
}

/** Upsert rows, idempotently, in one D1 batch. */
export async function upsertRows(
  env: IndexDbEnv,
  table: string,
  rows: Array<Record<string, unknown>>,
  onConflict: string,
): Promise<void> {
  if (rows.length === 0) return;
  const database = db(env);
  const statements = rows.map((row) => {
    const columns = Object.keys(row).sort();
    return database
      .prepare(upsertSql(table, columns, onConflict))
      .bind(...columns.map((column) => bindValue(row[column])));
  });
  await database.batch(statements);
}

/**
 * Recompute one trace row from `digitrace_spans_index`, in one statement.
 *
 * The SQLite port of `refresh_digitrace_trace` (Postgres migration 144): span
 * count, the activity window and duration, the root name/status, an error
 * status that never downgrades, and the first session/run id. One UPDATE is
 * atomic in D1, so two slices of a trace refreshing at once both converge on
 * the full-span aggregate (the Postgres version needed an advisory lock for
 * the same property because it read and wrote in separate statements).
 * The timestamps carry millisecond precision, so the duration is rounded to
 * whole milliseconds to drop julianday's floating-point residue.
 */
export const REFRESH_TRACE_SQL = `
UPDATE digitrace_traces AS t SET
  span_count = a.n,
  started_at = a.started,
  ended_at = a.ended,
  duration_ms = CASE WHEN a.ended IS NULL THEN NULL
    ELSE max(round((julianday(a.ended) - julianday(a.started)) * 86400000.0), 0) END,
  status = CASE WHEN a.any_error = 1 OR t.status = 'STATUS_CODE_ERROR'
    THEN 'STATUS_CODE_ERROR' ELSE coalesce(a.root_status, t.status) END,
  status_message = CASE WHEN a.any_error = 1 OR t.status = 'STATUS_CODE_ERROR'
    THEN coalesce(a.failed_message, t.status_message)
    ELSE coalesce(a.root_message, t.status_message) END,
  name = coalesce(a.root_name, t.name),
  session_id = coalesce(t.session_id, a.session),
  run_id = coalesce(t.run_id, a.run)
FROM (
  SELECT
    count(*) AS n,
    min(s.started_at) AS started,
    CASE WHEN sum(s.ended_at IS NULL) > 0 THEN NULL ELSE max(s.ended_at) END AS ended,
    coalesce(max(s.status = 'STATUS_CODE_ERROR'), 0) AS any_error,
    (SELECT r.name FROM digitrace_spans_index r WHERE r.workspace_id = ?1 AND r.trace_id = ?2
       AND r.parent_span_id IS NULL ORDER BY r.started_at, r.span_id LIMIT 1) AS root_name,
    (SELECT r.status FROM digitrace_spans_index r WHERE r.workspace_id = ?1 AND r.trace_id = ?2
       AND r.parent_span_id IS NULL ORDER BY r.started_at, r.span_id LIMIT 1) AS root_status,
    (SELECT r.status_message FROM digitrace_spans_index r WHERE r.workspace_id = ?1
       AND r.trace_id = ?2 AND r.parent_span_id IS NULL AND r.status_message IS NOT NULL
       ORDER BY r.started_at, r.span_id LIMIT 1) AS root_message,
    (SELECT r.status_message FROM digitrace_spans_index r WHERE r.workspace_id = ?1
       AND r.trace_id = ?2 AND r.status = 'STATUS_CODE_ERROR' AND r.status_message IS NOT NULL
       ORDER BY r.started_at, r.span_id LIMIT 1) AS failed_message,
    (SELECT r.session_id FROM digitrace_spans_index r WHERE r.workspace_id = ?1
       AND r.trace_id = ?2 AND r.session_id IS NOT NULL
       ORDER BY r.started_at, r.span_id LIMIT 1) AS session,
    (SELECT r.run_id FROM digitrace_spans_index r WHERE r.workspace_id = ?1
       AND r.trace_id = ?2 AND r.run_id IS NOT NULL
       ORDER BY r.started_at, r.span_id LIMIT 1) AS run
  FROM digitrace_spans_index s
  WHERE s.workspace_id = ?1 AND s.trace_id = ?2
) AS a
WHERE t.workspace_id = ?1 AND t.trace_id = ?2 AND a.n > 0`;

export async function refreshTraceRow(
  env: IndexDbEnv,
  workspaceId: string,
  traceId: string,
): Promise<void> {
  if (workspaceId === "" || traceId === "") {
    throw new Error("refreshTraceRow: a workspace id and a non-empty trace id are required");
  }
  await db(env).prepare(REFRESH_TRACE_SQL).bind(workspaceId, traceId).run();
}
