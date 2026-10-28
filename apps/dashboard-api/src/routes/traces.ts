/**
 * digitrace Traces tab reads (DIG-2661, ADR-0036 section 9).
 *
 * The tab reads the Supabase `public` index written by the digitrace consumer
 * (`digitrace_traces`, `digitrace_spans_index`, `digitrace_scores`) through the
 * existing dashboard-api worker. No new public path, no new hostname: the
 * routes are mounted on the same worker as every other read.
 *
 * ============================================================================
 * The tenant boundary is HERE, not in RLS (ADR-0036 section 5, DIG-2664 M6)
 * ============================================================================
 * dashboard-api reads with the service role, and service-role access bypasses
 * RLS. The tenant boundary on this path is therefore the application-layer
 * filter in this file:
 *
 *   1. every PostgREST query carries exactly one `workspace_id=eq.<tenant>`
 *      predicate — the caller's workspace, resolved once by `tenantWorkspace`;
 *   2. every row is re-checked after the read (`onlyWorkspace`) and a row from
 *      another workspace is dropped before it can reach the response.
 *
 * Step 2 is deliberate belt-and-braces: a future edit that drops the predicate
 * from a query, or an upstream that ignores it, must still not leak a client's
 * traces. `traces.test.ts` pins both steps with an upstream that returns rows
 * from two workspaces.
 *
 * `tenant_slug` and `tenant_slug_verified` are NOT columns on the index rows
 * (they are edge values on the archived batch object), so there is exactly one
 * column to filter on here: `workspace_id`.
 *
 * Cost is the index's own `cost_usd` / token columns, which the consumer writes
 * from the payload. The Workers Analytics Engine aggregates are the source of
 * record for cost (ADR-0036 section 9); until the WAE spike has run, this view
 * says so in `cost_source`/`cost_caveat` rather than implying it is the record.
 */

import { buildProvenance, errorResponse, type Provenance } from "../errors";
import { HOUSE_WORKSPACE_ID } from "../supabase";
import { tableRows, type TableReadEnv } from "../table-read";
import type { RouteCtx, RouteModule } from "./registry";

export type TracesEnv = TableReadEnv & {
  /**
   * The workspace this deployment serves. The edge does not pass a per-caller
   * workspace claim today, so the tenant is the deployment's workspace, and it
   * is resolved in exactly one place. An unset or malformed value falls back to
   * the house workspace rather than widening the read.
   */
  DASHBOARD_WORKSPACE_ID?: string;
};

type Row = Record<string, unknown>;

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TRACE_ID_RE = /^[0-9a-f]{32}$/i;
const SEARCH_RE = /^[A-Za-z0-9 ._:@/-]{1,120}$/;
const DAY_RE = /^\d{4}-\d{2}-\d{2}$/;
const MAX_LIST_LIMIT = 200;
const MAX_SPANS = 1000;
const MAX_COST_ROWS = 5000;

/** The one place the tenant is resolved. Never returns null, never widens. */
export function tenantWorkspace(env: TracesEnv): string {
  const v = (env.DASHBOARD_WORKSPACE_ID ?? "").trim();
  return UUID_RE.test(v) ? v.toLowerCase() : HOUSE_WORKSPACE_ID;
}

/** Rows that belong to the caller's workspace only. Exported for the M6 test. */
export function onlyWorkspace(rows: readonly Row[], workspace: string): Row[] {
  const want = workspace.toLowerCase();
  return rows.filter(
    (r) => typeof r.workspace_id === "string" && r.workspace_id.toLowerCase() === want,
  );
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null;
}

function num(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function pinOf(req: Request): { pin: string | null } | { error: Response } {
  const pin = new URL(req.url).searchParams.get("retrieval_pin");
  if (pin !== null && pin.length > 128) {
    return {
      error: errorResponse("bad_request", "retrieval_pin exceeds 128 characters", null, {
        max_length: 128,
      }),
    };
  }
  return { pin };
}

function ok(
  data: unknown,
  source: string,
  pin: string | null,
  asOf: string | null,
  marks: Provenance["marks"] = "stored",
): Response {
  return Response.json({
    data,
    as_of: asOf,
    retrieval_pin: pin,
    provenance: buildProvenance({ source, tip_date: asOf, marks }),
  });
}

// --- row shapes -------------------------------------------------------------

export interface TraceRow {
  trace_id: string;
  name: string | null;
  source: string | null;
  service_name: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  status: string | null;
  status_message: string | null;
  session_id: string | null;
  run_id: string | null;
  span_count: number | null;
}

export interface SpanRow {
  span_id: string;
  parent_span_id: string | null;
  name: string | null;
  kind: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  status: string | null;
  status_message: string | null;
  model: string | null;
  provider: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  cost_usd: number | null;
  /** true when the span carried a content hash (the text itself is never indexed). */
  has_content: boolean;
  /** Nested children, built by `buildSpanTree`. */
  children: SpanNode[];
}

export type SpanNode = SpanRow;

const TRACE_SELECT =
  "workspace_id,trace_id,name,source,service_name,started_at,ended_at,duration_ms,status,status_message,session_id,run_id,span_count";
const SPAN_SELECT =
  "workspace_id,trace_id,span_id,parent_span_id,name,kind,started_at,ended_at,duration_ms,status,status_message,model,provider,input_tokens,output_tokens,total_tokens,cost_usd,input_hash,output_hash";

export function traceRow(r: Row): TraceRow {
  return {
    trace_id: str(r.trace_id) ?? "",
    name: str(r.name),
    source: str(r.source),
    service_name: str(r.service_name),
    started_at: str(r.started_at),
    ended_at: str(r.ended_at),
    duration_ms: num(r.duration_ms),
    status: str(r.status),
    status_message: str(r.status_message),
    session_id: str(r.session_id),
    run_id: str(r.run_id),
    span_count: num(r.span_count),
  };
}

export function spanRow(r: Row): SpanRow {
  return {
    span_id: str(r.span_id) ?? "",
    parent_span_id: str(r.parent_span_id),
    name: str(r.name),
    kind: str(r.kind),
    started_at: str(r.started_at),
    ended_at: str(r.ended_at),
    duration_ms: num(r.duration_ms),
    status: str(r.status),
    status_message: str(r.status_message),
    model: str(r.model),
    provider: str(r.provider),
    input_tokens: num(r.input_tokens),
    output_tokens: num(r.output_tokens),
    total_tokens: num(r.total_tokens),
    cost_usd: num(r.cost_usd),
    has_content: str(r.input_hash) !== null || str(r.output_hash) !== null,
    children: [],
  };
}

/**
 * Build the span tree from flat index rows. Input order is not trusted: roots
 * are spans with no parent (or a parent that is not in the page), and siblings
 * keep the upstream order (started_at ascending). A span whose parent appears
 * later is still attached — the map is built before the edges are walked.
 *
 * A corrupt parent cycle must not make spans disappear or recurse forever: a
 * span on a cycle is surfaced as a root, and so is a span whose parent is on
 * one. Losing a span to a bad edge would hide exactly the trace the operator
 * came to read.
 */
export function buildSpanTree(spans: readonly SpanRow[]): SpanNode[] {
  const byId = new Map<string, SpanRow>();
  for (const s of spans) {
    if (s.span_id === "" || byId.has(s.span_id)) continue;
    byId.set(s.span_id, { ...s, children: [] });
  }
  const cyclic = new Set<string>();
  for (const s of byId.values()) {
    const seen = new Set<string>([s.span_id]);
    let cur = s;
    while (cur.parent_span_id !== null) {
      const parent = byId.get(cur.parent_span_id);
      if (parent === undefined) break;
      if (seen.has(parent.span_id)) {
        cyclic.add(s.span_id);
        break;
      }
      seen.add(parent.span_id);
      cur = parent;
    }
  }
  const roots: SpanNode[] = [];
  for (const s of byId.values()) {
    if (cyclic.has(s.span_id)) {
      roots.push(s);
      continue;
    }
    const parent = s.parent_span_id === null ? null : byId.get(s.parent_span_id);
    if (parent === null || parent === undefined) roots.push(s);
    else if (cyclic.has(parent.span_id)) roots.push(s);
    else parent.children.push(s);
  }
  return roots;
}

// --- queries ----------------------------------------------------------------

export interface ListParams {
  workspace: string;
  q: string | null;
  since: string | null;
  until: string | null;
  status: string | null;
  sessionId: string | null;
  runId: string | null;
  limit: number;
}

/** The PostgREST query for the list/search route. Exported so its one tenant pin is testable. */
export function listQuery(p: ListParams): string {
  const parts = [
    `select=${TRACE_SELECT}`,
    `workspace_id=eq.${p.workspace}`,
    "order=started_at.desc",
    `limit=${p.limit}`,
  ];
  if (p.since !== null) parts.push(`started_at=gte.${p.since}T00:00:00Z`);
  if (p.until !== null) parts.push(`started_at=lte.${p.until}T23:59:59.999Z`);
  if (p.status !== null) parts.push(`status=eq.${encodeURIComponent(p.status)}`);
  if (p.sessionId !== null) parts.push(`session_id=eq.${encodeURIComponent(p.sessionId)}`);
  if (p.runId !== null) parts.push(`run_id=eq.${encodeURIComponent(p.runId)}`);
  if (p.q !== null) {
    if (TRACE_ID_RE.test(p.q)) parts.push(`trace_id=eq.${p.q.toLowerCase()}`);
    else
      parts.push(
        `or=(name.ilike.*${encodeURIComponent(p.q)}*,service_name.ilike.*${encodeURIComponent(p.q)}*)`,
      );
  }
  return parts.join("&");
}

function parseList(
  req: Request,
  env: TracesEnv,
  pin: string | null,
): { params: ListParams } | { error: Response } {
  const u = new URL(req.url).searchParams;
  const q = u.get("q");
  if (q !== null && !SEARCH_RE.test(q)) {
    return {
      error: errorResponse(
        "bad_request",
        "q must be 1-120 characters of letters, digits, space, . _ : @ / -",
        pin,
        { q },
      ),
    };
  }
  for (const key of ["since", "until"] as const) {
    const v = u.get(key);
    if (v !== null && !DAY_RE.test(v)) {
      return {
        error: errorResponse("bad_request", `${key} must be YYYY-MM-DD`, pin, { [key]: v }),
      };
    }
  }
  const rawLimit = u.get("limit");
  let limit = 50;
  if (rawLimit !== null) {
    const n = Number(rawLimit);
    if (!Number.isInteger(n) || n < 1 || n > MAX_LIST_LIMIT) {
      return {
        error: errorResponse("bad_request", `limit must be an integer 1-${MAX_LIST_LIMIT}`, pin, {
          limit: rawLimit,
        }),
      };
    }
    limit = n;
  }
  const status = u.get("status");
  if (status !== null && !SEARCH_RE.test(status)) {
    return {
      error: errorResponse("bad_request", "status is not a valid status value", pin, { status }),
    };
  }
  const sessionId = u.get("session_id");
  if (sessionId !== null && !SEARCH_RE.test(sessionId)) {
    return {
      error: errorResponse("bad_request", "session_id is not a valid id", pin, {
        session_id: sessionId,
      }),
    };
  }
  const runId = u.get("run_id");
  if (runId !== null && !SEARCH_RE.test(runId)) {
    return {
      error: errorResponse("bad_request", "run_id is not a valid id", pin, { run_id: runId }),
    };
  }
  return {
    params: {
      workspace: tenantWorkspace(env),
      q: q === null || q.trim() === "" ? null : q.trim(),
      since: u.get("since"),
      until: u.get("until"),
      status,
      sessionId,
      runId,
      limit,
    },
  };
}

// --- handlers ---------------------------------------------------------------

/** GET /traces — list and search the caller's traces, newest first. */
async function list(req: Request, ctx: RouteCtx<TracesEnv>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const pR = parseList(req, ctx.env, pinR.pin);
  if ("error" in pR) return pR.error;
  const p = pR.params;
  const out = await tableRows(ctx.env, {
    table: "digitrace_traces",
    query: listQuery(p),
    allowEmpty: true,
    retrievalPin: pinR.pin,
  });
  if ("error" in out) return out.error;
  const rows = onlyWorkspace(out.rows, p.workspace);
  const traces = rows.map(traceRow);
  return ok(
    {
      workspace_id: p.workspace,
      traces,
      count: traces.length,
      window: { since: p.since, until: p.until },
      // An empty window is an honest empty, not an error: a quiet tenant has no traces.
      empty: traces.length === 0,
    },
    "core:digitrace_traces",
    pinR.pin,
    traces.length > 0 ? traces[0]!.started_at : null,
  );
}

/** GET /traces/{trace_id} — one trace, its span tree and its scores. */
async function detail(req: Request, ctx: RouteCtx<TracesEnv>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const traceId = (ctx.params.trace_id ?? "").trim().toLowerCase();
  if (!TRACE_ID_RE.test(traceId)) {
    return errorResponse("bad_request", "trace_id must be 32 hex characters", pinR.pin, {
      trace_id: traceId,
    });
  }
  const ws = tenantWorkspace(ctx.env);
  const traceOut = await tableRows(ctx.env, {
    table: "digitrace_traces",
    query: `select=${TRACE_SELECT}&workspace_id=eq.${ws}&trace_id=eq.${traceId}&limit=1`,
    allowEmpty: true,
    retrievalPin: pinR.pin,
  });
  if ("error" in traceOut) return traceOut.error;
  const traceRows = onlyWorkspace(traceOut.rows, ws);
  if (traceRows.length === 0) {
    return errorResponse("not_found", "trace not found in this workspace", pinR.pin, {
      trace_id: traceId,
    });
  }
  const trace = traceRow(traceRows[0]!);

  const [spanOut, scoreOut] = await Promise.all([
    tableRows(ctx.env, {
      table: "digitrace_spans_index",
      query: `select=${SPAN_SELECT}&workspace_id=eq.${ws}&trace_id=eq.${traceId}&order=started_at.asc&limit=${MAX_SPANS}`,
      allowEmpty: true,
      retrievalPin: pinR.pin,
    }),
    tableRows(ctx.env, {
      table: "digitrace_scores",
      query: `select=workspace_id,span_id,name,value,value_text,source,created_at&workspace_id=eq.${ws}&trace_id=eq.${traceId}&limit=200`,
      allowEmpty: true,
      retrievalPin: pinR.pin,
    }),
  ]);
  if ("error" in spanOut) return spanOut.error;
  if ("error" in scoreOut) return scoreOut.error;

  const spans = onlyWorkspace(spanOut.rows, ws).map(spanRow);
  const tree = buildSpanTree(spans);
  const scores = onlyWorkspace(scoreOut.rows, ws).map((r) => ({
    span_id: str(r.span_id) ?? "",
    name: str(r.name) ?? "",
    value: num(r.value),
    value_text: str(r.value_text),
    source: str(r.source),
    created_at: str(r.created_at),
  }));

  return ok(
    {
      workspace_id: ws,
      trace,
      // A trace row can land before its spans are flushed (the consumer updates
      // the row from the spans index). Empty here is "pending", not "no spans".
      spans_pending: spans.length === 0 && (trace.span_count ?? 0) > 0,
      span_count: spans.length,
      spans: tree,
      scores,
      token_total: spans.reduce((n, s) => n + (s.total_tokens ?? 0), 0),
      cost_total_usd: spans.reduce((n, s) => n + (s.cost_usd ?? 0), 0),
    },
    "core:digitrace_spans_index",
    pinR.pin,
    trace.started_at,
  );
}

interface CostBucket {
  model: string | null;
  provider: string | null;
  spans: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

/** Fold span rows into per-model token/cost buckets. Exported for tests. */
export function foldCost(rows: readonly Row[]): CostBucket[] {
  const byKey = new Map<string, CostBucket>();
  for (const r of rows) {
    const model = str(r.model);
    const provider = str(r.provider);
    const key = `${provider ?? ""}\u0000${model ?? ""}`;
    let b = byKey.get(key);
    if (b === undefined) {
      b = {
        model,
        provider,
        spans: 0,
        input_tokens: 0,
        output_tokens: 0,
        total_tokens: 0,
        cost_usd: 0,
      };
      byKey.set(key, b);
    }
    b.spans += 1;
    b.input_tokens += num(r.input_tokens) ?? 0;
    b.output_tokens += num(r.output_tokens) ?? 0;
    b.total_tokens += num(r.total_tokens) ?? 0;
    b.cost_usd += num(r.cost_usd) ?? 0;
  }
  return [...byKey.values()].sort((a, b) => b.cost_usd - a.cost_usd);
}

/** GET /traces/cost — tokens and cost per model over a window, from the index. */
async function cost(req: Request, ctx: RouteCtx<TracesEnv>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const u = new URL(req.url).searchParams;
  for (const key of ["since", "until"] as const) {
    const v = u.get(key);
    if (v !== null && !DAY_RE.test(v)) {
      return errorResponse("bad_request", `${key} must be YYYY-MM-DD`, pinR.pin, { [key]: v });
    }
  }
  const since = u.get("since");
  const until = u.get("until");
  const ws = tenantWorkspace(ctx.env);
  const parts = [
    "select=workspace_id,model,provider,input_tokens,output_tokens,total_tokens,cost_usd",
    `workspace_id=eq.${ws}`,
    "order=started_at.desc",
    `limit=${MAX_COST_ROWS}`,
  ];
  if (since !== null) parts.push(`started_at=gte.${since}T00:00:00Z`);
  if (until !== null) parts.push(`started_at=lte.${until}T23:59:59.999Z`);
  const out = await tableRows(ctx.env, {
    table: "digitrace_spans_index",
    query: parts.join("&"),
    allowEmpty: true,
    retrievalPin: pinR.pin,
  });
  if ("error" in out) return out.error;
  const rows = onlyWorkspace(out.rows, ws);
  const buckets = foldCost(rows);
  const totals = buckets.reduce(
    (t, b) => ({
      spans: t.spans + b.spans,
      input_tokens: t.input_tokens + b.input_tokens,
      output_tokens: t.output_tokens + b.output_tokens,
      total_tokens: t.total_tokens + b.total_tokens,
      cost_usd: t.cost_usd + b.cost_usd,
    }),
    { spans: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0, cost_usd: 0 },
  );
  return ok(
    {
      workspace_id: ws,
      window: { since, until },
      totals,
      by_model: buckets,
      /**
       * Honest provenance for the money column. ADR-0036 makes the Workers
       * Analytics Engine aggregates the source of record; those are
       * fire-and-forget, sampled under load and have no read-after-write
       * guarantee, and the WAE spike has not run. Until it has, this is the
       * index's own figure and is labelled as such.
       */
      cost_source: "index",
      cost_caveat:
        "summed from digitrace_spans_index; the Workers Analytics Engine aggregate is the source of record and the AI Gateway logs are the cross-check",
      truncated: rows.length >= MAX_COST_ROWS,
    },
    "core:digitrace_spans_index",
    pinR.pin,
    null,
  );
}

export const registerTraces: RouteModule<TracesEnv> = (reg) => {
  reg.get("/traces", list);
  reg.get("/traces/cost", cost);
  reg.get("/traces/{trace_id}", detail);
};
