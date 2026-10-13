import { selectSql, upsertSql } from "./query";
import type { Backend, Env, SelectQuery, UpsertQuery } from "./types";

export class D1Backend implements Backend {
  readonly name = "d1" as const;
  constructor(private db: D1Database) {}
  async select(q: SelectQuery) {
    const { sql, binds } = selectSql(q);
    const r = await this.db.prepare(sql).bind(...binds).all();
    return r.results as Record<string, unknown>[];
  }
  async upsert(q: UpsertQuery) {
    const stmts = q.rows.map((row) => {
      const { sql, binds } = upsertSql(q, row);
      return this.db.prepare(sql).bind(...binds);
    });
    await this.db.batch(stmts); // one implicit transaction
    return { written: q.rows.length };
  }
}

/** PostgREST passthrough so callers can switch to this API before the data moves. */
export class SupabaseBackend implements Backend {
  readonly name = "supabase" as const;
  constructor(private url: string, private key: string, private fetcher: typeof fetch = fetch) {}
  private headers(extra: Record<string, string> = {}) {
    return { apikey: this.key, Authorization: `Bearer ${this.key}`, "Content-Type": "application/json", ...extra };
  }
  async select(q: SelectQuery) {
    const p = new URLSearchParams();
    if (q.columns) p.set("select", q.columns.join(","));
    for (const f of q.filters) p.append(f.column, f.op === "in" ? `in.(${(f.value as string[]).join(",")})` : `${f.op}.${f.value}`);
    if (q.order.length) p.set("order", q.order.map((o) => `${o.column}.${o.desc ? "desc" : "asc"}`).join(","));
    p.set("limit", String(q.limit));
    const r = await this.fetcher(`${this.url}/rest/v1/${q.table}?${p}`, { headers: this.headers() });
    if (!r.ok) throw new Error(`supabase select ${q.table}: ${r.status}`);
    return (await r.json()) as Record<string, unknown>[];
  }
  async upsert(q: UpsertQuery) {
    const r = await this.fetcher(`${this.url}/rest/v1/${q.table}?on_conflict=${q.onConflict.join(",")}`, {
      method: "POST",
      headers: this.headers({ Prefer: "resolution=merge-duplicates,return=minimal" }),
      body: JSON.stringify(q.rows),
    });
    if (!r.ok) throw new Error(`supabase upsert ${q.table}: ${r.status}`);
    return { written: q.rows.length };
  }
}

/** Supabase stays the default until a project is cut over (DIG-2902/2903). */
export function pickBackend(env: Env, db: "twelvex"): Backend {
  const mode = (env.DATA_BACKEND ?? "supabase").toLowerCase();
  if (mode === "d1") {
    if (!env.TWELVEX_DB) throw new Error("DATA_BACKEND=d1 but TWELVEX_DB binding missing");
    return new D1Backend(env.TWELVEX_DB);
  }
  if (mode !== "supabase") throw new Error(`unknown DATA_BACKEND ${mode}`);
  if (!env.SUPABASE_TWELVEX_URL || !env.SUPABASE_TWELVEX_SERVICE_KEY) throw new Error(`supabase backend for ${db} not configured`);
  return new SupabaseBackend(env.SUPABASE_TWELVEX_URL, env.SUPABASE_TWELVEX_SERVICE_KEY);
}
