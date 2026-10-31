import { describe, expect, it } from "vitest";
import {
  bindValue,
  D1ConfigError,
  REFRESH_TRACE_SQL,
  refreshTraceRow,
  resolveWorkspaceId,
  upsertRows,
  upsertSql,
} from "./d1";
import { CONFLICT_TARGETS } from "./index-rows";

interface Recorded {
  sql: string;
  binds: unknown[];
  via: "batch" | "run";
}

/** A D1 stand-in that records statements; no database, no network. */
function fakeD1(options: { fail?: boolean } = {}) {
  const recorded: Recorded[] = [];
  const statement = (sql: string) => {
    const s = {
      sql,
      binds: [] as unknown[],
      bind(...values: unknown[]) {
        s.binds = values;
        return s;
      },
      async run() {
        if (options.fail) throw new Error("D1_ERROR: boom");
        recorded.push({ sql, binds: s.binds, via: "run" });
        return { success: true };
      },
    };
    return s;
  };
  const db = {
    prepare: statement,
    async batch(statements: Array<{ sql: string; binds: unknown[] }>) {
      if (options.fail) throw new Error("D1_ERROR: boom");
      for (const s of statements) recorded.push({ sql: s.sql, binds: s.binds, via: "batch" });
      return [];
    },
  };
  return { db: db as unknown as D1Database, recorded };
}

describe("bindValue", () => {
  it("stores objects as JSON text and maps the rest to D1 types", () => {
    expect(bindValue({ a: 1 })).toBe('{"a":1}');
    expect(bindValue(undefined)).toBeNull();
    expect(bindValue(null)).toBeNull();
    expect(bindValue(Number.NaN)).toBeNull();
    expect(bindValue(true)).toBe(1);
    expect(bindValue(3.5)).toBe(3.5);
    expect(bindValue("x")).toBe("x");
  });
});

describe("upsertSql", () => {
  it("upserts on the natural key and never rewrites the key columns", () => {
    const sql = upsertSql(
      "digitrace_traces",
      ["name", "trace_id", "workspace_id"],
      CONFLICT_TARGETS.traces,
    );
    expect(sql).toBe(
      "INSERT INTO digitrace_traces (name, trace_id, workspace_id) VALUES (?1, ?2, ?3) " +
        "ON CONFLICT (workspace_id, trace_id) DO UPDATE SET name = excluded.name",
    );
  });

  it("refuses a table the consumer does not own", () => {
    expect(() => upsertSql("digitrace_sessions", ["x"], "workspace_id,session_id")).toThrow(
      /not writable/,
    );
  });

  it("refuses a conflict target that is not the table's key", () => {
    expect(() => upsertSql("digitrace_spans_index", ["a"], "trace_id")).toThrow(/conflict/);
  });

  it("refuses a column name that is not an identifier", () => {
    expect(() =>
      upsertSql("digitrace_traces", ["name; DROP TABLE x"], CONFLICT_TARGETS.traces),
    ).toThrow(/bad column/);
  });
});

describe("upsertRows", () => {
  it("writes every row as one batch with JSON-encoded objects", async () => {
    const { db, recorded } = fakeD1();
    await upsertRows(
      { INDEX_DB: db },
      "digitrace_spans_index",
      [
        { workspace_id: "tenant-a", trace_id: "t", span_id: "s1", attributes: { k: "v" } },
        { workspace_id: "tenant-a", trace_id: "t", span_id: "s2", attributes: {} },
      ],
      CONFLICT_TARGETS.spans,
    );
    expect(recorded).toHaveLength(2);
    expect(recorded.every((r) => r.via === "batch")).toBe(true);
    // Columns are sorted: attributes, span_id, trace_id, workspace_id.
    expect(recorded[0].binds).toEqual(['{"k":"v"}', "s1", "t", "tenant-a"]);
  });

  it("does nothing for no rows, even without a binding", async () => {
    await expect(upsertRows({}, "digitrace_traces", [], CONFLICT_TARGETS.traces)).resolves.toBe(
      undefined,
    );
  });

  it("names the missing binding instead of writing nowhere", async () => {
    await expect(
      upsertRows({}, "digitrace_traces", [{ workspace_id: "a" }], CONFLICT_TARGETS.traces),
    ).rejects.toBeInstanceOf(D1ConfigError);
  });

  it("surfaces a D1 failure so the consumer retries", async () => {
    const { db } = fakeD1({ fail: true });
    await expect(
      upsertRows(
        { INDEX_DB: db },
        "digitrace_traces",
        [{ workspace_id: "a", trace_id: "t" }],
        CONFLICT_TARGETS.traces,
      ),
    ).rejects.toThrow(/D1_ERROR/);
  });
});

describe("refreshTraceRow", () => {
  it("recomputes one trace, scoped to its tenant, in one statement", async () => {
    const { db, recorded } = fakeD1();
    await refreshTraceRow({ INDEX_DB: db }, "tenant-a", "trace-1");
    expect(recorded).toEqual([
      { sql: REFRESH_TRACE_SQL, binds: ["tenant-a", "trace-1"], via: "run" },
    ]);
  });

  it("filters every subquery on the tenant and the trace", () => {
    const tenantFilters = REFRESH_TRACE_SQL.match(/workspace_id = \?1/g) ?? [];
    const traceFilters = REFRESH_TRACE_SQL.match(/trace_id = \?2/g) ?? [];
    // six ordered lookups + the aggregate + the target row
    expect(tenantFilters).toHaveLength(8);
    expect(traceFilters).toHaveLength(8);
    expect(REFRESH_TRACE_SQL).toContain("'STATUS_CODE_ERROR'");
  });

  it("refuses an empty trace id", async () => {
    const { db } = fakeD1();
    await expect(refreshTraceRow({ INDEX_DB: db }, "tenant-a", "")).rejects.toThrow(/trace id/);
  });
});

describe("resolveWorkspaceId", () => {
  it("uses the verified tenant slug as the tenancy key", async () => {
    await expect(resolveWorkspaceId({}, "tenant-a")).resolves.toBe("tenant-a");
  });
});
