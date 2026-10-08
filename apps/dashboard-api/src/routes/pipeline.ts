/**
 * Phase 2 — pipeline reads. Cost and token fields stay null: run_health
 * does not project them. A missing node_runs table leaves the static graph
 * with null states rather than invented run health.
 */

import { buildProvenance, errorResponse, type Provenance } from "../errors";
import { HOUSE_WORKSPACE_ID } from "../supabase";
import { tableRows, type TableReadEnv } from "../table-read";
import type { RouteCtx, RouteModule } from "./registry";

type Row = Record<string, unknown>;
type Env = TableReadEnv;

/** Static pipeline stages. States come only from node_runs. */
export const STATIC_GRAPH = [
  { id: "ingest", label: "Ingest", stage: "collect", col: 0, to: ["research"] },
  { id: "research", label: "Research", stage: "research", col: 1, to: ["decide"] },
  { id: "decide", label: "Decide", stage: "decide", col: 2, to: ["publish"] },
  { id: "publish", label: "Publish", stage: "publish", col: 3, to: [] as string[] },
] as const;

function num(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim().length > 0 ? v.trim() : null;
}

function pinOf(req: Request): { pin: string | null } | { error: Response } {
  const pin = new URL(req.url).searchParams.get("retrieval_pin");
  if (pin !== null && pin.length > 128) {
    return { error: errorResponse("bad_request", "retrieval_pin exceeds 128 characters", null, { max_length: 128 }) };
  }
  return { pin };
}

function dateFilter(req: Request, pin: string | null): { date: string | null } | { error: Response } {
  const date = new URL(req.url).searchParams.get("date");
  if (date === null) return { date: null };
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return { error: errorResponse("bad_request", "date must be YYYY-MM-DD", pin, { date }) };
  }
  return { date };
}

function ok(data: unknown, source: string, pin: string | null, asOf: string | null, marks: Provenance["marks"] = "stored"): Response {
  return Response.json({
    data,
    as_of: asOf,
    retrieval_pin: pin,
    provenance: buildProvenance({ source, tip_date: asOf, marks }),
  });
}

async function read(env: Env, table: string, query: string): Promise<{ rows: Row[] } | { error: Response }> {
  return tableRows(env, { table, query, allowEmpty: true });
}

async function health(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const dateR = dateFilter(req, pinR.pin);
  if ("error" in dateR) return dateR.error;
  const filter = dateR.date ? `&run_date=eq.${dateR.date}` : "";
  const out = await read(ctx.env, "run_health", `select=*&order=run_date.desc&limit=1${filter}`);
  if ("error" in out) return out.error;
  const row = out.rows[0];
  const runDate = row ? str(row.run_date)?.slice(0, 10) ?? null : null;
  return ok(
    {
      run_date: runDate,
      run_type: row ? str(row.run_type) : null,
      status: row ? str(row.status) : null,
      config: row ? str(row.model) : null,
      posture: null,
      nodes: row
        ? { ok: num(row.segments_ok), carried: num(row.segments_carried), failed: num(row.segments_failed) }
        : null,
      inputs_calls: { persisted: null, note: "call counts are not on run_health" },
      calls: null,
      tokens_in: null,
      tokens_out: null,
      cost_usd: null,
    },
    "core:run_health",
    pinR.pin,
    runDate,
  );
}

async function graph(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const runs = await tableRows(ctx.env, {
    table: "node_runs",
    query: "select=run_id,node_name,outcome,started_at&order=started_at.desc&limit=200",
    allowEmpty: true,
  });
  const failed = "error" in runs;
  const all = "error" in runs ? [] : runs.rows;
  // Latest run only. node_name is the pipeline's own node id; a static stage gets a
  // state only on an exact match, never a guessed mapping.
  const runId = str(all[0]?.run_id);
  const rows = runId === null ? [] : all.filter((r) => str(r.run_id) === runId);
  const runDate = str(rows.at(-1)?.started_at ?? rows[0]?.started_at)?.slice(0, 10) ?? null;
  const stateFor = (id: string): string | null => {
    const hit = rows.find((r) => str(r.node_name) === id);
    return hit ? str(hit.outcome) : null;
  };
  return ok(
    {
      run_date: runDate,
      selected_node: STATIC_GRAPH[0].id,
      nodes: STATIC_GRAPH.map((n) => ({ ...n, to: [...n.to], state: stateFor(n.id) })),
    },
    failed ? "static-graph" : "core:node_runs",
    pinR.pin,
    runDate,
    failed ? "unavailable" : "stored",
  );
}

async function trace(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const out = await read(
    ctx.env,
    "run_event_trace",
    "select=run_id,run_date,name,operation,status,duration_ms,sequence&order=run_date.desc,sequence.desc&limit=200",
  );
  if ("error" in out) return out.error;
  const runId = str(out.rows[0]?.run_id);
  const latest = runId === null ? [] : out.rows.filter((r) => str(r.run_id) === runId);
  const rows = latest.map((r) => {
    const ms = num(r.duration_ms);
    return {
      node: str(r.name) ?? str(r.operation) ?? "",
      calls: null,
      duration_s: ms === null ? null : ms / 1000,
      state: str(r.status),
    };
  }).filter((r) => r.node !== "");
  const runDate = str(latest[0]?.run_date)?.slice(0, 10) ?? null;
  return ok({ rows }, "core:run_event_trace", pinR.pin, runDate);
}

/** House-workspace documents, newest first. `documents` is per-workspace (migration 105). */
function houseDocs(env: Env, select: string, extra = "", limit = 200) {
  return read(env, "documents", `select=${select}&workspace_id=eq.${HOUSE_WORKSPACE_ID}${extra}&order=date.desc&limit=${limit}`);
}

function paragraphsOf(content: string | null): string[] {
  return content ? content.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean) : [];
}

async function narrative(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  // The run's narrative is its Daily Digest.
  const out = await houseDocs(ctx.env, "date,title,content", "&doc_type=eq.Daily%20Digest", 1);
  if ("error" in out) return out.error;
  const row = out.rows[0];
  const runDate = row ? str(row.date)?.slice(0, 10) ?? null : null;
  return ok(
    { run_date: runDate, heading: row ? str(row.title) : null, paragraphs: paragraphsOf(row ? str(row.content) : null) },
    "core:documents",
    pinR.pin,
    runDate,
  );
}

async function artifacts(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const out = await houseDocs(ctx.env, "date,title,category,document_key,content");
  if ("error" in out) return out.error;
  const tip = str(out.rows[0]?.date);
  const rows = out.rows.filter((r) => str(r.date) === tip).map((r) => ({
    stage: str(r.category),
    node: str(r.document_key) ?? str(r.title) ?? "",
    document: str(r.title),
    date: str(r.date)?.slice(0, 10) ?? null,
    state_only: str(r.content) === null,
  })).filter((r) => r.node !== "");
  return ok({ rows }, "core:documents", pinR.pin, tip?.slice(0, 10) ?? null);
}

async function nodeDocument(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const node = new URL(req.url).searchParams.get("node") ?? ctx.params.node ?? "selected";
  const out = await houseDocs(ctx.env, "date,title,document_key,content");
  if ("error" in out) return out.error;
  const row = node === "selected"
    ? out.rows[0]
    : out.rows.find((r) => str(r.document_key) === node);
  const runDate = row ? str(row.date)?.slice(0, 10) ?? null : null;
  return ok(
    {
      run_date: runDate,
      node_id: row ? str(row.document_key) ?? node : node,
      title: row ? str(row.title) : null,
      paragraphs: paragraphsOf(row ? str(row.content) : null),
      note: row ? null : "no document for this node",
    },
    "core:documents",
    pinR.pin,
    runDate,
  );
}

export const registerPipeline: RouteModule<Env> = (reg) => {
  reg.get("/pipeline/runs/latest/health", health);
  reg.get("/pipeline/runs/latest/graph", graph);
  reg.get("/pipeline/runs/latest/narrative", narrative);
  reg.get("/pipeline/runs/latest/trace", trace);
  reg.get("/pipeline/runs/latest/artifacts", artifacts);
  reg.get("/pipeline/runs/latest/nodes/selected/document", nodeDocument);
};
