import type { Filter, Order, SelectQuery, TableSpec, UpsertQuery } from "./types";

export const MAX_LIMIT = 1000;
const OPS = new Set(["eq", "gte", "lte", "gt", "lt", "in"]);

export class BadRequest extends Error {}

function col(spec: TableSpec, c: string): string {
  if (!spec.columns.includes(c)) throw new BadRequest(`unknown column ${c}`);
  return c;
}

/** Parse PostgREST-style params (?col=eq.v&order=col.desc&limit=n&select=a,b) against an allowlist. */
export function parseSelect(table: string, spec: TableSpec, params: URLSearchParams): SelectQuery {
  const filters: Filter[] = [];
  const order: Order[] = [];
  let limit = 100;
  let columns: string[] | null = null;
  for (const [k, v] of params) {
    if (k === "limit") {
      const n = Number(v);
      if (!Number.isInteger(n) || n < 1) throw new BadRequest("bad limit");
      limit = Math.min(n, MAX_LIMIT);
    } else if (k === "order") {
      for (const part of v.split(",")) {
        const [c, dir = "asc"] = part.split(".");
        if (dir !== "asc" && dir !== "desc") throw new BadRequest("bad order");
        order.push({ column: col(spec, c), desc: dir === "desc" });
      }
    } else if (k === "select") {
      columns = v.split(",").map((c) => col(spec, c.trim()));
    } else {
      const dot = v.indexOf(".");
      const op = v.slice(0, dot);
      if (dot < 1 || !OPS.has(op)) throw new BadRequest(`bad filter ${k}`);
      const raw = v.slice(dot + 1);
      const value = op === "in" ? raw.replace(/^\(|\)$/g, "").split(",") : raw;
      filters.push({ column: col(spec, k), op: op as Filter["op"], value });
    }
  }
  return { table, columns, filters, order, limit };
}

export function validateUpsert(table: string, spec: TableSpec, body: unknown, onConflict: string | null): UpsertQuery {
  const rows = Array.isArray(body) ? body : [body];
  if (rows.length === 0 || rows.length > 500) throw new BadRequest("1..500 rows per call");
  for (const r of rows) {
    if (!r || typeof r !== "object" || Array.isArray(r)) throw new BadRequest("rows must be objects");
    for (const k of Object.keys(r)) col(spec, k);
  }
  const conflict = onConflict ? onConflict.split(",").map((c) => col(spec, c)) : spec.pk;
  if (conflict.length === 0) throw new BadRequest("table has no primary key; pass on_conflict");
  return { table, rows: rows as Record<string, unknown>[], onConflict: conflict };
}

const SQL_OP = { eq: "=", gte: ">=", lte: "<=", gt: ">", lt: "<" } as const;

/** Parameterized SQLite. Identifiers come only from the allowlist, values only as binds. */
export function selectSql(q: SelectQuery): { sql: string; binds: unknown[] } {
  const binds: unknown[] = [];
  const where = q.filters.map((f) => {
    if (f.op === "in") {
      const vs = f.value as string[];
      binds.push(...vs);
      return `"${f.column}" IN (${vs.map(() => "?").join(",")})`;
    }
    binds.push(f.value);
    return `"${f.column}" ${SQL_OP[f.op]} ?`;
  });
  const cols = q.columns ? q.columns.map((c) => `"${c}"`).join(",") : "*";
  let sql = `SELECT ${cols} FROM "${q.table}"`;
  if (where.length) sql += ` WHERE ${where.join(" AND ")}`;
  if (q.order.length) sql += ` ORDER BY ${q.order.map((o) => `"${o.column}" ${o.desc ? "DESC" : "ASC"}`).join(",")}`;
  sql += ` LIMIT ${q.limit}`;
  return { sql, binds };
}

/** D1 stores json/arrays/booleans as TEXT/INTEGER (see d1/twelvex/0001_init.sql). */
export function toSqlValue(v: unknown): unknown {
  if (v === undefined) return null;
  if (typeof v === "boolean") return v ? 1 : 0;
  if (v !== null && typeof v === "object") return JSON.stringify(v);
  return v;
}

export function upsertSql(q: UpsertQuery, row: Record<string, unknown>): { sql: string; binds: unknown[] } {
  const cols = Object.keys(row);
  const updates = cols.filter((c) => !q.onConflict.includes(c));
  const set = updates.length ? `DO UPDATE SET ${updates.map((c) => `"${c}"=excluded."${c}"`).join(",")}` : "DO NOTHING";
  return {
    sql: `INSERT INTO "${q.table}" (${cols.map((c) => `"${c}"`).join(",")}) VALUES (${cols.map(() => "?").join(",")}) ON CONFLICT (${q.onConflict.map((c) => `"${c}"`).join(",")}) ${set}`,
    binds: cols.map((c) => toSqlValue(row[c])),
  };
}
