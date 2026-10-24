/**
 * Shared enveloped PostgREST read for domain routes. Unlike the bare-row
 * `/v1/tables/*` proxy this returns the standard §1 envelope
 * `{ data, as_of, retrieval_pin, provenance }` and fails closed: a missing
 * env, an upstream error, or (unless `allowEmpty`) zero rows is a 502
 * `upstream_empty` — never invented or defaulted data.
 *
 * `core` reads the house Supabase project; `twelvex` reads the separate
 * twelve-x project (TWELVEX_SUPABASE_URL / TWELVEX_SUPABASE_SERVICE_KEY,
 * both optional; absent = fail closed).
 */

import { buildProvenance, errorResponse, type Provenance } from "./errors";
import { UpstreamError, hasSupabaseEnv, supaGet, type SupabaseEnv } from "./supabase";

export interface TableReadEnv extends SupabaseEnv {
  TWELVEX_SUPABASE_URL?: string;
  TWELVEX_SUPABASE_SERVICE_KEY?: string;
}

export type TableProject = "core" | "twelvex";

export interface TableReadOpts {
  project?: TableProject;
  table: string;
  /** PostgREST query string without the table, e.g. `select=*&order=date.desc&limit=10`. */
  query?: string;
  /** Row field whose max value becomes `as_of` / `provenance.tip_date` (ISO date or timestamp). */
  asOfField?: string;
  /** Serve `[]` as a success instead of `upstream_empty`. Default false. */
  allowEmpty?: boolean;
  retrievalPin?: string | null;
  provenance?: Partial<Provenance>;
}

/** The twelve-x project as a SupabaseEnv, or null when unconfigured. */
export function twelvexEnv(env: TableReadEnv): SupabaseEnv | null {
  const e: SupabaseEnv = { SUPABASE_URL: env.TWELVEX_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY: env.TWELVEX_SUPABASE_SERVICE_KEY };
  return hasSupabaseEnv(e) ? e : null;
}

function projectEnv(env: TableReadEnv, project: TableProject): SupabaseEnv | null {
  return project === "twelvex" ? twelvexEnv(env) : hasSupabaseEnv(env) ? env : null;
}

/** Raw rows or a fail-closed error Response. Domain handlers that reshape rows build on this. */
export async function tableRows(env: TableReadEnv, opts: TableReadOpts): Promise<{ rows: Record<string, unknown>[] } | { error: Response }> {
  const pin = opts.retrievalPin ?? null;
  const project = opts.project ?? "core";
  const penv = projectEnv(env, project);
  if (!penv) return { error: errorResponse("upstream_empty", `${project} supabase is not configured`, pin, { project, table: opts.table }) };
  let rows: unknown;
  try {
    rows = await supaGet(penv, opts.query ? `${opts.table}?${opts.query}` : opts.table);
  } catch (err) {
    if (err instanceof UpstreamError) {
      return { error: errorResponse("upstream_empty", err.message, pin, { project, table: opts.table, upstream_status: err.status }) };
    }
    throw err;
  }
  if (!Array.isArray(rows)) return { error: errorResponse("upstream_empty", `${opts.table} returned a non-list body`, pin, { project, table: opts.table }) };
  if (rows.length === 0 && !opts.allowEmpty) return { error: errorResponse("upstream_empty", `${opts.table} returned no rows`, pin, { project, table: opts.table }) };
  return { rows: rows as Record<string, unknown>[] };
}

function maxOf(rows: Record<string, unknown>[], field: string): string | null {
  let best: string | null = null;
  for (const r of rows) {
    const v = r[field];
    if (typeof v === "string" && v.length > 0 && (best === null || v > best)) best = v;
  }
  return best;
}

/** Enveloped read: `{ data: rows, as_of, retrieval_pin, provenance }`. */
export async function tableRead(env: TableReadEnv, opts: TableReadOpts): Promise<Response> {
  const out = await tableRows(env, opts);
  if ("error" in out) return out.error;
  const tip = opts.asOfField ? maxOf(out.rows, opts.asOfField) : null;
  return Response.json({
    data: out.rows,
    as_of: tip ? tip.slice(0, 10) : null,
    retrieval_pin: opts.retrievalPin ?? null,
    provenance: buildProvenance({ source: `${opts.project ?? "core"}:${opts.table}`, tip_date: tip ? tip.slice(0, 10) : null, ...opts.provenance }),
  });
}

/** twelve-x reader: enveloped read over the twelve-x project; fail closed when it is not configured. */
export function twelvexRead(env: TableReadEnv, opts: Omit<TableReadOpts, "project">): Promise<Response> {
  return tableRead(env, { ...opts, project: "twelvex" });
}
