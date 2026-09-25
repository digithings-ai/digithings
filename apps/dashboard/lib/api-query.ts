/**
 * PostgREST-flavoured read builder backed by the dashboard Workers API.
 *
 * Slice 0008 rewire: this shim lets the ported call sites keep their
 * builder-chain shape (`from().select().eq().order().limit()`) while every
 * read executes as `GET /v1/tables/:table` through `lib/api-client.ts`.
 * The service-role key lives only in the Worker; the bundle sends no
 * Supabase credentials. House scoping (`workspace_id`) is enforced
 * server-side by the Worker for house tables — see CONTRACT §7.
 *
 * The builder is thenable: `await apiDb.from('theses').select('*')`
 * resolves `{ data, error }`, mirroring the supabase-js result shape so
 * downstream assert/log/mapping logic ports unchanged.
 */
import {
  apiMaybeSingle,
  apiTable,
  type TableOrder,
  type TableRead,
} from './api-client';

/** Internal accumulated filter before it is folded into a {@link TableRead}. */
type PendingFilter = {
  op: 'eq' | 'ilike' | 'like' | 'in' | 'lt' | 'lte' | 'gt' | 'gte';
  column: string;
  value: unknown;
};

export class ApiQueryBuilder {
  private selectCols = '*';
  private readonly orders: TableOrder[] = [];
  private limitN?: number;
  private offsetN?: number;
  private readonly filters: PendingFilter[] = [];

  constructor(private readonly table: string) {}

  select(cols = '*'): this {
    this.selectCols = cols;
    return this;
  }

  eq(column: string, value: unknown): this {
    this.filters.push({ op: 'eq', column, value });
    return this;
  }

  ilike(column: string, value: string): this {
    this.filters.push({ op: 'ilike', column, value });
    return this;
  }

  like(column: string, value: string): this {
    this.filters.push({ op: 'like', column, value });
    return this;
  }

  in(column: string, value: unknown[]): this {
    this.filters.push({ op: 'in', column, value });
    return this;
  }

  lt(column: string, value: unknown): this {
    this.filters.push({ op: 'lt', column, value });
    return this;
  }

  lte(column: string, value: unknown): this {
    this.filters.push({ op: 'lte', column, value });
    return this;
  }

  gt(column: string, value: unknown): this {
    this.filters.push({ op: 'gt', column, value });
    return this;
  }

  gte(column: string, value: unknown): this {
    this.filters.push({ op: 'gte', column, value });
    return this;
  }

  order(column: string, opts?: { ascending?: boolean }): this {
    this.orders.push({ column, ascending: opts?.ascending ?? true });
    return this;
  }

  limit(n: number): this {
    this.limitN = n;
    return this;
  }

  /** PostgREST inclusive range → offset/limit. */
  range(from: number, to: number): this {
    this.offsetN = from;
    this.limitN = to - from + 1;
    return this;
  }

  private buildQuery(): TableRead {
    const q: TableRead = { select: this.selectCols };
    if (this.orders.length > 0) q.order = [...this.orders];
    if (this.limitN !== undefined) q.limit = this.limitN;
    if (this.offsetN !== undefined) q.offset = this.offsetN;
    for (const f of this.filters) {
      const value = Array.isArray(f.value) ? (f.value as Array<string | number>) : f.value;
      if (f.op === 'in') {
        q.in = { ...(q.in ?? {}), [f.column]: value as Array<string | number> };
      } else {
        const map = (q as unknown as Record<string, Record<string, string | number>>)[f.op] ?? {};
        map[f.column] = value as string | number;
        (q as unknown as Record<string, Record<string, string | number>>)[f.op] = map;
      }
    }
    return q;
  }

  /** Execute as a multi-row read. Never throws — errors come back as `{ data: null, error }`. */
  async exec(): Promise<{ data: any; error: unknown }> {
    try {
      const data = await apiTable(this.table, this.buildQuery());
      return { data, error: null };
    } catch (error) {
      return { data: null, error };
    }
  }

  /**
   * Execute as a maybe-single read (first row or null). Never throws.
   * Mirrors PostgREST `.maybeSingle()`.
   */
  async maybeSingle(): Promise<{ data: any; error: unknown }> {
    try {
      const data = await apiMaybeSingle(this.table, this.buildQuery());
      return { data, error: null };
    } catch (error) {
      return { data: null, error };
    }
  }

  /** Thenable so `await builder` resolves `{ data, error }`. */
  then<TResult1 = { data: any; error: unknown }, TResult2 = never>(
    onfulfilled?: ((value: { data: any; error: unknown }) => TResult1 | PromiseLike<TResult1>) | null,
    onrejected?: ((reason: unknown) => TResult2 | PromiseLike<TResult2>) | null,
  ): Promise<TResult1 | TResult2> {
    return this.exec().then(onfulfilled, onrejected);
  }
}

/** Root entry point — replaces the Supabase client value at read call sites. */
export const apiDb = {
  from(table: string): ApiQueryBuilder {
    return new ApiQueryBuilder(table);
  },
};

export type ApiDb = typeof apiDb;

/**
 * House-book read entry point — replaces `houseBook(supabase, table, columns)`.
 * The workspace pin is enforced server-side by the Worker (CONTRACT §7);
 * the table union mirrors `HouseBookTable` in `lib/house-workspace.ts`.
 */
export function apiHouseBook(
  table: 'positions' | 'position_events' | 'portfolio_metrics',
  columns = '*',
): ApiQueryBuilder {
  return new ApiQueryBuilder(table).select(columns);
}
