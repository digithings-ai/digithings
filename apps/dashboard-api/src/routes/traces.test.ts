import { afterEach, describe, expect, it, vi } from "vitest";
import app, { type Env } from "../index";
import {
  buildSpanTree,
  foldCost,
  listQuery,
  onlyWorkspace,
  spanRow,
  tenantWorkspace,
} from "./traces";

/**
 * DIG-2661 / DIG-2664 M6 — the app-layer tenant filter.
 *
 * dashboard-api reads the digitrace index with the service role, and
 * service-role access bypasses RLS. These tests are the proof that the filter
 * in `traces.ts`, and not RLS, isolates each client's traces: the mocked
 * upstream deliberately returns rows from TWO workspaces, and the response must
 * carry only the caller's.
 */

const WS_A = "6b753576-ced9-5319-9bfa-c5d0aacd9319";
const WS_B = "11111111-2222-3333-4444-555555555555";
const TRACE_A = "a".repeat(32);
const TRACE_B = "b".repeat(32);

const ENV: Env = {
  DASHBOARD_TRUST_IDENTITY_HEADERS: "1",
  DASHBOARD_DEV_CALLER: "enterprise+12x",
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "core-key",
  DASHBOARD_WORKSPACE_ID: WS_A,
};

const urls: string[] = [];

function mockFetch(handler: (url: string) => unknown | { status: number }): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const u = String(url);
      urls.push(u);
      const out = handler(u);
      if (out && typeof out === "object" && !Array.isArray(out) && "status" in out) {
        return Response.json(
          { message: "missing" },
          { status: (out as { status: number }).status },
        );
      }
      return Response.json(out);
    }),
  );
}

function traceRowOf(workspaceId: string, traceId: string, startedAt: string, name: string) {
  return {
    workspace_id: workspaceId,
    trace_id: traceId,
    name,
    source: "otel",
    service_name: "digichat",
    started_at: startedAt,
    ended_at: startedAt,
    duration_ms: 1200,
    status: "ok",
    status_message: null,
    session_id: "s1",
    run_id: null,
    span_count: 2,
  };
}

function spanRowOf(
  workspaceId: string,
  traceId: string,
  spanId: string,
  parent: string | null,
  startedAt: string,
) {
  return {
    workspace_id: workspaceId,
    trace_id: traceId,
    span_id: spanId,
    parent_span_id: parent,
    name: `span-${spanId}`,
    kind: "llm",
    started_at: startedAt,
    ended_at: startedAt,
    duration_ms: 10,
    status: "ok",
    status_message: null,
    model: "gpt-test",
    provider: "openai",
    input_tokens: 10,
    output_tokens: 5,
    total_tokens: 15,
    cost_usd: 0.02,
    input_hash: "h",
    output_hash: null,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  urls.length = 0;
});

describe("tenant filter (DIG-2664 M6)", () => {
  it("the list route returns only the caller workspace when upstream returns two", async () => {
    mockFetch((u) =>
      u.includes("digitrace_traces")
        ? [
            traceRowOf(WS_A, TRACE_A, "2026-10-27T10:00:00Z", "ours"),
            traceRowOf(WS_B, TRACE_B, "2026-10-27T11:00:00Z", "theirs"),
          ]
        : [],
    );
    const res = await app.fetch(new Request("https://x/traces"), ENV);
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      data: { traces: { trace_id: string; name: string }[]; count: number };
    };
    expect(body.data.traces.map((t) => t.trace_id)).toEqual([TRACE_A]);
    expect(body.data.count).toBe(1);
    // The predicate is on the wire, not only in memory.
    const traceUrl = urls.find((u) => u.includes("digitrace_traces")) ?? "";
    expect(traceUrl).toContain(`workspace_id=eq.${WS_A}`);
    expect(traceUrl).not.toContain(WS_B);
  });

  it("the detail route drops spans and scores from another workspace", async () => {
    mockFetch((u) => {
      if (u.includes("digitrace_traces"))
        return [traceRowOf(WS_A, TRACE_A, "2026-10-27T10:00:00Z", "ours")];
      if (u.includes("digitrace_spans_index"))
        return [
          spanRowOf(WS_A, TRACE_A, "s1", null, "2026-10-27T10:00:00Z"),
          spanRowOf(WS_B, TRACE_B, "x1", null, "2026-10-27T10:00:01Z"),
        ];
      if (u.includes("digitrace_scores"))
        return [
          {
            workspace_id: WS_A,
            trace_id: TRACE_A,
            span_id: "",
            name: "quality",
            value: 1,
            value_text: null,
            source: "mlflow",
            created_at: "2026-10-27T10:01:00Z",
          },
          {
            workspace_id: WS_B,
            trace_id: TRACE_B,
            span_id: "",
            name: "leak",
            value: 1,
            value_text: null,
            source: "mlflow",
            created_at: "2026-10-27T10:01:00Z",
          },
        ];
      return [];
    });
    const res = await app.fetch(new Request(`https://x/traces/${TRACE_A}`), ENV);
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      data: {
        span_count: number;
        spans: { span_id: string }[];
        scores: { name: string }[];
        workspace_id: string;
      };
    };
    expect(body.data.workspace_id).toBe(WS_A);
    expect(body.data.span_count).toBe(1);
    expect(body.data.spans.map((s) => s.span_id)).toEqual(["s1"]);
    expect(body.data.scores.map((s) => s.name)).toEqual(["quality"]);
    for (const u of urls) {
      if (u.includes("workspace_id=eq.")) expect(u).not.toContain(WS_B);
    }
  });

  it("onlyWorkspace is exact on the column and case-insensitive on the uuid", () => {
    const rows = [
      { workspace_id: WS_A },
      { workspace_id: WS_A.toUpperCase() },
      { workspace_id: WS_B },
      {},
    ];
    expect(onlyWorkspace(rows, WS_A)).toHaveLength(2);
  });

  it("an unset or malformed deployment workspace falls back to house, never to no filter", () => {
    expect(tenantWorkspace({} as Env)).toBe(WS_A);
    expect(tenantWorkspace({ DASHBOARD_WORKSPACE_ID: "not-a-uuid" } as Env)).toBe(WS_A);
    expect(tenantWorkspace({ DASHBOARD_WORKSPACE_ID: WS_B } as Env)).toBe(WS_B);
  });

  it("every list query carries exactly one workspace pin", () => {
    const q = listQuery({
      workspace: WS_A,
      q: null,
      since: null,
      until: null,
      status: null,
      sessionId: null,
      runId: null,
      limit: 50,
    });
    expect(q.match(/workspace_id=/g)).toHaveLength(1);
    expect(q).toContain(`workspace_id=eq.${WS_A}`);
  });
});

describe("GET /traces", () => {
  it("searches name and service_name with a validated term", async () => {
    mockFetch((u) =>
      u.includes("digitrace_traces")
        ? [traceRowOf(WS_A, TRACE_A, "2026-10-27T10:00:00Z", "chat turn")]
        : [],
    );
    const res = await app.fetch(
      new Request("https://x/traces?q=chat&since=2026-10-01&limit=10"),
      ENV,
    );
    expect(res.status).toBe(200);
    const u = urls.find((x) => x.includes("digitrace_traces")) ?? "";
    expect(u).toContain("or=(name.ilike.*chat*,service_name.ilike.*chat*)");
    expect(u).toContain("started_at=gte.2026-10-01T00:00:00Z");
    expect(u).toContain("limit=10");
  });

  it("an exact 32-hex term searches trace_id, not a like", () => {
    const q = listQuery({
      workspace: WS_A,
      q: TRACE_A,
      since: null,
      until: null,
      status: null,
      sessionId: null,
      runId: null,
      limit: 50,
    });
    expect(q).toContain(`trace_id=eq.${TRACE_A}`);
    expect(q).not.toContain("ilike");
  });

  it("refuses a q that could break the PostgREST filter", async () => {
    mockFetch(() => []);
    const res = await app.fetch(
      new Request(`https://x/traces?q=${encodeURIComponent("a,b)c*")}`),
      ENV,
    );
    expect(res.status).toBe(400);
    expect(urls).toHaveLength(0);
  });

  it("refuses an out-of-range limit", async () => {
    mockFetch(() => []);
    expect((await app.fetch(new Request("https://x/traces?limit=5000"), ENV)).status).toBe(400);
  });

  it("an empty window is an empty list, not a 502", async () => {
    mockFetch(() => []);
    const res = await app.fetch(new Request("https://x/traces"), ENV);
    expect(res.status).toBe(200);
    const body = (await res.json()) as { data: { traces: unknown[]; empty: boolean } };
    expect(body.data.traces).toEqual([]);
    expect(body.data.empty).toBe(true);
  });
});

describe("GET /traces/{trace_id}", () => {
  it("is 404 when the trace is not in the caller workspace", async () => {
    mockFetch((u) =>
      u.includes("digitrace_traces")
        ? [traceRowOf(WS_B, TRACE_B, "2026-10-27T10:00:00Z", "theirs")]
        : [],
    );
    const res = await app.fetch(new Request(`https://x/traces/${TRACE_A}`), ENV);
    expect(res.status).toBe(404);
  });

  it("is 400 on a malformed trace id and never calls upstream", async () => {
    mockFetch(() => []);
    expect((await app.fetch(new Request("https://x/traces/nope"), ENV)).status).toBe(400);
    expect(urls).toHaveLength(0);
  });

  it("flags pending spans when the row counts spans the index does not have yet", async () => {
    mockFetch((u) => {
      if (u.includes("digitrace_traces"))
        return [traceRowOf(WS_A, TRACE_A, "2026-10-27T10:00:00Z", "ours")];
      return [];
    });
    const res = await app.fetch(new Request(`https://x/traces/${TRACE_A}`), ENV);
    const body = (await res.json()) as { data: { spans_pending: boolean; span_count: number } };
    expect(body.data.span_count).toBe(0);
    expect(body.data.spans_pending).toBe(true);
  });
});

describe("span tree", () => {
  it("nests children under their parent and keeps orphans as roots", () => {
    const rows = [
      spanRow({ span_id: "c1", parent_span_id: "p", started_at: "2026-10-27T10:00:02Z" }),
      spanRow({ span_id: "p", parent_span_id: null, started_at: "2026-10-27T10:00:00Z" }),
      spanRow({ span_id: "c2", parent_span_id: "p", started_at: "2026-10-27T10:00:03Z" }),
      spanRow({ span_id: "orphan", parent_span_id: "missing", started_at: "2026-10-27T10:00:04Z" }),
    ];
    const tree = buildSpanTree(rows);
    expect(tree.map((n) => n.span_id).sort()).toEqual(["orphan", "p"]);
    const p = tree.find((n) => n.span_id === "p")!;
    expect(p.children.map((n) => n.span_id)).toEqual(["c1", "c2"]);
  });

  it("does not hang on a parent cycle and never duplicates a span", () => {
    const rows = [
      spanRow({ span_id: "a", parent_span_id: "b" }),
      spanRow({ span_id: "b", parent_span_id: "a" }),
      spanRow({ span_id: "a", parent_span_id: null }),
    ];
    const tree = buildSpanTree(rows);
    const ids: string[] = [];
    const walk = (nodes: { span_id: string; children: unknown[] }[]) => {
      for (const n of nodes) {
        ids.push(n.span_id);
        walk(n.children as never[]);
      }
    };
    walk(tree);
    expect(ids.sort()).toEqual(["a", "b"]);
  });
});

describe("GET /traces/cost", () => {
  it("folds tokens and cost per model, tenant-scoped, and labels the source honestly", async () => {
    mockFetch((u) =>
      u.includes("digitrace_spans_index")
        ? [
            {
              workspace_id: WS_A,
              model: "m1",
              provider: "p",
              input_tokens: 10,
              output_tokens: 5,
              total_tokens: 15,
              cost_usd: 0.1,
            },
            {
              workspace_id: WS_A,
              model: "m1",
              provider: "p",
              input_tokens: 20,
              output_tokens: 5,
              total_tokens: 25,
              cost_usd: 0.2,
            },
            {
              workspace_id: WS_B,
              model: "m2",
              provider: "p",
              input_tokens: 99,
              output_tokens: 1,
              total_tokens: 100,
              cost_usd: 9.9,
            },
          ]
        : [],
    );
    const res = await app.fetch(new Request("https://x/traces/cost?since=2026-10-01"), ENV);
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      data: {
        totals: { spans: number; total_tokens: number; cost_usd: number };
        by_model: { model: string; cost_usd: number }[];
        cost_source: string;
        cost_caveat: string;
      };
    };
    expect(body.data.totals.spans).toBe(2);
    expect(body.data.totals.total_tokens).toBe(40);
    expect(body.data.totals.cost_usd).toBeCloseTo(0.3);
    expect(body.data.by_model.map((b) => b.model)).toEqual(["m1"]);
    expect(body.data.cost_source).toBe("index");
    expect(body.data.cost_caveat).toContain("Analytics Engine");
  });

  it("foldCost sums a model that appears under two providers separately", () => {
    const buckets = foldCost([
      { model: "m", provider: "a", total_tokens: 1, cost_usd: 1 },
      { model: "m", provider: "b", total_tokens: 2, cost_usd: 2 },
    ]);
    expect(buckets).toHaveLength(2);
    expect(buckets[0]!.cost_usd).toBe(2);
  });
});
