/**
 * A query-builder-compatible PostgREST data layer.
 *
 * WHY THIS EXISTS. The sibling `settings` edge function types its data layer as
 * `AdminClient = SupabaseClient` (`digiquant/supabase/functions/_shared/
 * supabase-admin.ts:11`). That is not a narrow interface — it is the whole
 * supabase-js client, so there is no seam to port: the handler chains
 * `.from().select().eq().order().limit().maybeSingle()` directly onto it.
 * Measured against that handler, the surface actually used is:
 *
 *   34 `.from`   27 `.select`   39 `.eq`   2 `.neq`   1 `.gte`
 *    7 `.order`   5 `.limit`   13 `.maybeSingle`   6 `.single`
 *    9 `.insert`  5 `.update`  2 `.upsert`
 *
 * across 12 tables. `prices-live` needed three narrow calls and therefore got a
 * narrow client; settings needs the builder, so this is the builder.
 *
 * WHAT IS PORTABLE. PostgREST is HTTP with query parameters. A fluent surface
 * that EMITS requests is pure: no network, no database, no D1 coupling. That
 * makes every semantic below assertable by comparing the emitted
 * `{url, method, headers, body}` — which is why this slice ships with the
 * emission tests and leaves execution to a thin `fetch` seam.
 *
 * WHAT IS DELIBERATELY NOT HERE. `rpc()`, `count`, storage, auth, and realtime
 * are absent on purpose: the census did not find them, so an absent method
 * throws rather than silently doing something wrong. Fail-closed beats
 * plausible. Supabase stays live and untouched (2-week rollback); nothing here
 * is mounted, no `wrangler.toml` key, no secret, no deploy.
 */

export interface PostgrestError {
  /** PostgREST error code, e.g. `PGRST116`. `null` when the body was not a PostgREST error. */
  code: string | null;
  message: string;
  details: string | null;
  hint: string | null;
}

export interface PostgrestClientOptions {
  /** Base Supabase URL. A trailing slash is tolerated. */
  url: string;
  /** Service-role (or anon) key. */
  apiKey: string;
  /** Injection seam for tests. Defaults to global `fetch`. */
  fetchImpl?: typeof fetch;
}

/** The request a builder produced. Pure data — this is what the tests assert on. */
export interface PostgrestRequest {
  method: "GET" | "POST" | "PATCH" | "DELETE";
  url: string;
  headers: Record<string, string>;
  body: unknown;
}

type FilterOp = "eq" | "neq" | "gt" | "gte" | "lt" | "lte";

interface Filter {
  op: FilterOp | "in";
  column: string;
  value: string | number | ReadonlyArray<string | number>;
}

interface Order {
  column: string;
  ascending: boolean;
}

/** `single()` asks PostgREST for an object; `maybeSingle()` filters locally. */
type Cardinality = "many" | "one" | "atMostOne";

function encodeValue(value: string | number): string {
  // PostgREST filters are `col=eq.<value>`; commas and parentheses inside the
  // value would otherwise close the list early.
  return encodeURIComponent(String(value))
    .replace(/%2C/g, ",")
    .replace(/%28/g, "(")
    .replace(/%29/g, ")");
}

/**
 * The builder. Every method returns `this` so chains compose; `then` makes the
 * chain awaitable the way `await supabase.from(...)` is.
 */
export class PostgrestBuilder<T = unknown> implements PromiseLike<T> {
  private readonly base: string;
  private readonly apiKey: string;
  private readonly fetchImpl: typeof fetch;
  private readonly table: string;
  private columns: string[] | null = null;
  private readonly filters: Filter[] = [];
  private readonly orders: Order[] = [];
  private method: PostgrestRequest["method"] = "GET";
  private payload: unknown = undefined;
  private readonly prefer: string[] = [];
  private limitCount: number | null = null;
  private offsetCount: number | null = null;
  private cardinality: Cardinality = "many";
  private conflict: string | null = null;

  constructor(base: string, apiKey: string, fetchImpl: typeof fetch, table: string) {
    this.base = base;
    this.apiKey = apiKey;
    this.fetchImpl = fetchImpl;
    this.table = table;
  }

  /** Project columns. Required before a read, exactly as PostgREST requires it on GET. */
  select(columns = "*"): this {
    if (this.columns !== null) {
      throw new Error("postgrest: select() may only be called once per query");
    }
    this.columns = [columns];
    return this;
  }

  private filter(op: FilterOp, column: string, value: string | number): this {
    this.filters.push({ op, column, value });
    return this;
  }

  eq(column: string, value: string | number): this {
    return this.filter("eq", column, value);
  }

  neq(column: string, value: string | number): this {
    return this.filter("neq", column, value);
  }

  gt(column: string, value: string | number): this {
    return this.filter("gt", column, value);
  }

  gte(column: string, value: string | number): this {
    return this.filter("gte", column, value);
  }

  lt(column: string, value: string | number): this {
    return this.filter("lt", column, value);
  }

  lte(column: string, value: string | number): this {
    return this.filter("lte", column, value);
  }

  /** `col=in.(a,b,c)`. */
  in(column: string, values: ReadonlyArray<string | number>): this {
    if (!Array.isArray(values)) {
      throw new Error("postgrest: in() requires an array");
    }
    this.filters.push({ op: "in", column, value: values });
    return this;
  }

  order(column: string, options: { ascending?: boolean } = {}): this {
    this.orders.push({ column, ascending: options.ascending !== false });
    return this;
  }

  limit(count: number): this {
    this.limitCount = count;
    return this;
  }

  range(from: number, to: number): this {
    this.limitCount = to - from + 1;
    this.offsetCount = from;
    return this;
  }

  /**
   * Exactly one row, or throw. PostgREST answers `406 PGRST116` when the
   * projection yields zero or many rows, which is why this sets the object
   * Accept header rather than checking a count locally.
   */
  single(): this {
    this.cardinality = "one";
    return this;
  }

  /**
   * Zero or one row: `null` on zero, throw on more than one. supabase-js does
   * this with `limit(1)` plus a local length check, NOT with the object
   * Accept header — so `maybeSingle` on an empty result must NOT be an error.
   * The distinction is load-bearing and is pinned by both arms of the tests.
   */
  maybeSingle(): this {
    this.cardinality = "atMostOne";
    if (this.limitCount === null) this.limitCount = 1;
    return this;
  }

  insert(rows: unknown): this {
    if (this.method !== "GET") {
      throw new Error("postgrest: a query may only have one write method");
    }
    this.method = "POST";
    this.payload = rows;
    this.prefer.push("return=representation");
    return this;
  }

  upsert(rows: unknown, options: { onConflict?: string } = {}): this {
    if (this.method !== "GET") {
      throw new Error("postgrest: a query may only have one write method");
    }
    this.method = "POST";
    this.payload = rows;
    // MUST be merge-duplicates. `resolution=ignore-duplicates` here would make
    // every repeat a no-op, which is the same class of silent freeze the
    // prices-live upsert guard exists to prevent.
    this.prefer.push("resolution=merge-duplicates");
    if (options.onConflict) this.conflict = options.onConflict;
    return this;
  }

  update(patch: unknown): this {
    if (this.method !== "GET") {
      throw new Error("postgrest: a query may only have one write method");
    }
    this.method = "PATCH";
    this.payload = patch;
    this.prefer.push("return=representation");
    return this;
  }

  delete(): this {
    if (this.method !== "GET") {
      throw new Error("postgrest: a query may only have one write method");
    }
    this.method = "DELETE";
    this.prefer.push("return=representation");
    return this;
  }

  /** The pure part: turn the accumulated chain into a request. */
  buildRequest(): PostgrestRequest {
    if (this.columns === null && this.method === "GET") {
      // PostgREST rejects a GET with no projection. Failing here is clearer
      // than letting the server 400 on a whole-table read.
      throw new Error("postgrest: select() is required before reading");
    }

    const query: string[] = [];
    if (this.columns !== null) query.push(`select=${this.columns.join(",")}`);
    for (const f of this.filters) {
      if (f.op === "in") {
        const list = (f.value as ReadonlyArray<string | number>)
          .map((v) => encodeValue(v as string | number))
          .join(",");
        query.push(`${f.column}=in.(${list})`);
      } else {
        query.push(`${f.column}=${f.op}.${encodeValue(f.value as string | number)}`);
      }
    }
    for (const o of this.orders) {
      query.push(`order=${o.column}.${o.ascending ? "asc" : "desc"}`);
    }
    if (this.limitCount !== null) query.push(`limit=${this.limitCount}`);
    if (this.offsetCount !== null) query.push(`offset=${this.offsetCount}`);
    if (this.conflict) query.push(`on_conflict=${this.conflict}`);

    const headers: Record<string, string> = {
      apikey: this.apiKey,
      Authorization: `Bearer ${this.apiKey}`,
      "Content-Type": "application/json",
    };
    if (this.cardinality === "one") {
      headers.Accept = "application/vnd.pgrst.object+json";
    }
    if (this.prefer.length > 0) headers.Prefer = this.prefer.join(",");

    const qs = query.length > 0 ? `?${query.join("&")}` : "";
    return {
      method: this.method,
      url: `${this.base}/rest/v1/${this.table}${qs}`,
      headers,
      body: this.payload,
    };
  }

  /** Execute. Throws a `PostgrestError` so callers cannot mistake a failure for data. */
  async then<R1 = T, R2 = never>(
    onfulfilled?: ((value: T) => R1 | PromiseLike<R1>) | null,
    onrejected?: ((reason: unknown) => R2 | PromiseLike<R2>) | null,
  ): Promise<R1 | R2> {
    return this.execute().then(onfulfilled, onrejected);
  }

  private async execute(): Promise<T> {
    const req = this.buildRequest();
    const res = await this.fetchImpl(req.url, {
      method: req.method,
      headers: req.headers,
      body: req.body === undefined ? undefined : JSON.stringify(req.body),
    });
    const text = await res.text();
    let parsed: unknown = null;
    if (text.length > 0) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = null;
      }
    }

    if (!res.ok) {
      const err = (parsed ?? {}) as Partial<PostgrestError>;
      throw makeError(err.code ?? null, err.message ?? `HTTP ${res.status}`, err);
    }

    if (this.cardinality === "atMostOne") {
      const rows = Array.isArray(parsed) ? parsed : [];
      if (rows.length > 1) {
        throw makeError("PGRST116", "multiple rows returned for maybeSingle", null);
      }
      return (rows[0] ?? null) as T;
    }
    return parsed as T;
  }
}

function makeError(
  code: string | null,
  message: string,
  extra: Partial<PostgrestError> | null,
): PostgrestError {
  return {
    code,
    message,
    details: extra?.details ?? null,
    hint: extra?.hint ?? null,
  };
}

export interface PostgrestClient {
  from<T = unknown>(table: string): PostgrestBuilder<T>;
}

/** Build a client. Mirrors `createAdminClient` from the edge function. */
export function createPostgrestClient(options: PostgrestClientOptions): PostgrestClient {
  const base = options.url.replace(/\/+$/, "");
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  if (typeof fetchImpl !== "function") {
    throw new Error("postgrest: no fetch implementation available");
  }
  return {
    from<T>(table: string) {
      if (!table) throw new Error("postgrest: from() requires a table");
      return new PostgrestBuilder<T>(base, options.apiKey, fetchImpl, table);
    },
  };
}