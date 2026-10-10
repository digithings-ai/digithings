/**
 * Phase 4 — strategy catalog reads over the core `strategies` store.
 * Deployments, targets, and paper P&L have no table: those routes return a
 * typed empty state. Deploy stays "coming soon" (every step is `todo`).
 */

import { buildProvenance, errorResponse, type Provenance } from "../errors";
import { tableRows, type TableReadEnv } from "../table-read";
import type { RouteCtx, RouteModule } from "./registry";

type Row = Record<string, unknown>;
type Env = TableReadEnv;

const NO_DEPLOY = "no deployment store";
const SOON = "Deploy is not built yet.";

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

async function read(env: Env, table: string, query: string): Promise<{ rows: Row[] } | { error: Response }> {
  return tableRows(env, { table, query, allowEmpty: true });
}

function catalogRow(r: Row) {
  return {
    id: str(r.id) ?? "",
    name: str(r.label) ?? str(r.id) ?? "",
    family: str(r.engine),
    universe: str(r.symbol),
    cadence: null as string | null,
    targets: null as string[] | null,
    status: r.enabled === false ? "disabled" : "enabled",
    deploy: null as string | null,
  };
}

/** Stable pick: explicit `?id=`, else the first enabled id, else the first id. */
export function pickStrategy(rows: Row[], id: string | null): Row | null {
  if (id) return rows.find((r) => str(r.id) === id) ?? null;
  const enabled = rows.filter((r) => r.enabled !== false);
  const pool = enabled.length > 0 ? enabled : rows;
  return [...pool].sort((a, b) => (str(a.id) ?? "").localeCompare(str(b.id) ?? ""))[0] ?? null;
}

function parametersOf(config: unknown): { name: string; value: string | number | null; state: string | null }[] {
  if (config == null || typeof config !== "object" || Array.isArray(config)) return [];
  return Object.entries(config as Record<string, unknown>).map(([name, value]) => {
    if (typeof value === "number" && Number.isFinite(value)) return { name, value, state: null };
    if (typeof value === "string") return { name, value, state: null };
    if (typeof value === "boolean") return { name, value: value ? "true" : "false", state: null };
    if (value == null) return { name, value: null, state: null };
    return { name, value: null, state: "unparsed" };
  });
}

/** Stored tearsheet fields the landing card can print. Missing numbers stay null. */
export function tearsheetCard(row: Row | null, metrics: unknown): Record<string, unknown> | null {
  if (!row) return null;
  const m = metrics != null && typeof metrics === "object" && !Array.isArray(metrics) ? (metrics as Row) : {};
  const dca = m.dca != null && typeof m.dca === "object" && !Array.isArray(m.dca) ? (m.dca as Row) : {};
  return {
    id: str(row.id),
    name: str(m.label) ?? str(row.label) ?? str(row.id),
    symbol: str(m.symbol) ?? str(row.symbol),
    kind: str(m.kind) ?? str(row.engine),
    net_profit_pct: num(m.net_profit_pct),
    max_drawdown_pct: num(m.max_drawdown_pct),
    profit_factor: num(m.profit_factor),
    win_rate_pct: num(m.win_rate_pct),
    total_trades: num(m.total_trades),
    period_start: str(m.period_start),
    period_end: str(m.period_end),
    vs_lump_pct: num(dca.vs_lump_pct) ?? num(m.vs_lump_pct),
    allocated_pct: num(dca.allocated_pct) ?? num(m.allocated_pct),
  };
}

/** Dated points only. A bare number series is refused — dates are not invented. */
export function curvePoints(raw: unknown): { date: string; value: number | null }[] | null {
  if (!Array.isArray(raw) || raw.length === 0) return null;
  const points: { date: string; value: number | null }[] = [];
  for (const item of raw) {
    if (item == null || typeof item !== "object") return null;
    const rec = item as Row;
    const date = str(rec.date) ?? str(rec.t);
    if (!date) return null;
    points.push({ date: date.slice(0, 10), value: num(rec.value) ?? num(rec.v) ?? num(rec.nav) });
  }
  return points;
}

async function strategies(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const out = await read(ctx.env, "strategies", "select=id,symbol,label,engine,enabled,updated_at&order=id.asc&limit=200");
  if ("error" in out) return out.error;
  const asOf = out.rows.map((r) => str(r.updated_at)?.slice(0, 10)).filter((d): d is string => d !== null).sort().at(-1) ?? null;
  return ok(
    { strategies: out.rows.map(catalogRow).filter((r) => r.id !== "") },
    "core:strategies",
    pinR.pin,
    asOf,
  );
}

async function summary(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const out = await read(ctx.env, "strategies", "select=id,enabled,updated_at&limit=500");
  if ("error" in out) return out.error;
  const signals = await read(ctx.env, "strategy_signals", "select=last_signal_date,as_of&limit=500");
  if ("error" in signals) return signals.error;
  const last = signals.rows
    .map((r) => str(r.last_signal_date)?.slice(0, 10) ?? str(r.as_of)?.slice(0, 10))
    .filter((d): d is string => d !== null)
    .sort()
    .at(-1) ?? null;
  return ok(
    {
      catalog: out.rows.length,
      deployable: out.rows.filter((r) => r.enabled !== false).length,
      deployments: null,
      paper_accounts: null,
      portfolios: null,
      brokers: null,
      plan: null,
      last_run: last,
      notice: { tag: "soon" as const, text: SOON },
    },
    "core:strategies",
    pinR.pin,
    last,
  );
}

function deployments(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok({ deployments: [], empty_reason: NO_DEPLOY }, "core:strategies", pinR.pin, null, "unavailable");
}

function targets(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok({ targets: [] }, "core:strategies", pinR.pin, null, "unavailable");
}

async function one(req: Request, ctx: RouteCtx<Env>): Promise<{ pin: string | null; row: Row | null } | { error: Response }> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR;
  const id = new URL(req.url).searchParams.get("id");
  const out = await read(ctx.env, "strategies", "select=id,symbol,label,engine,enabled,config,updated_at&order=id.asc&limit=200");
  if ("error" in out) return out;
  return { pin: pinR.pin, row: pickStrategy(out.rows, id) };
}

async function overview(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const got = await one(req, ctx);
  if ("error" in got) return got.error;
  const row = got.row;
  return ok(
    {
      id: row ? str(row.id) : null,
      name: row ? str(row.label) ?? str(row.id) : null,
      lede: null,
      family: row ? str(row.engine) : null,
      universe: row ? str(row.symbol) : null,
      cadence: null,
      targets: null,
      related_thesis: null,
      execution: null,
    },
    "core:strategies",
    got.pin,
    row ? str(row.updated_at)?.slice(0, 10) ?? null : null,
  );
}

async function parameters(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const got = await one(req, ctx);
  if ("error" in got) return got.error;
  return ok(
    { parameters: got.row ? parametersOf(got.row.config) : [] },
    "core:strategies",
    got.pin,
    null,
    got.row ? "stored" : "unavailable",
  );
}

async function performance(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const got = await one(req, ctx);
  if ("error" in got) return got.error;
  if (!got.row) {
    return ok({ available: false, reason: "no strategy", points: [] }, "core:strategy_tearsheets", got.pin, null, "unavailable");
  }
  const id = str(got.row.id) ?? "";
  const sheets = await read(
    ctx.env,
    "strategy_tearsheets",
    `select=strategy_id,as_of,equity_curve,metrics&strategy_id=eq.${encodeURIComponent(id)}&limit=1`,
  );
  if ("error" in sheets) return sheets.error;
  const card = tearsheetCard(got.row, sheets.rows[0]?.metrics);
  const curve = curvePoints(sheets.rows[0]?.equity_curve);
  if (!curve) {
    return ok(
      { available: false, reason: "tearsheet has no dated curve", points: [], card },
      "core:strategy_tearsheets",
      got.pin,
      null,
      card ? "stored" : "unavailable",
    );
  }
  const asOf = str(sheets.rows[0]?.as_of)?.slice(0, 10) ?? curve.at(-1)?.date ?? null;
  return ok({ available: true, reason: null, points: curve, card }, "core:strategy_tearsheets", got.pin, asOf);
}

function runs(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok({ runs: [], empty_reason: NO_DEPLOY }, "core:strategies", pinR.pin, null, "unavailable");
}

function deployFlow(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok(
    {
      steps: [
        { label: "Choose a target", detail: "Paper only. Live deploy is not built.", state: "todo", status: "soon" },
        { label: "Set capital", detail: null, state: "todo", status: "soon" },
        { label: "Confirm", detail: "No order is sent.", state: "todo", status: "soon" },
      ],
    },
    "static:deploy-flow",
    pinR.pin,
    null,
    "unavailable",
  );
}

function deployDraft(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok(
    {
      target_kind: null,
      paper_capital: null,
      broker: null,
      portfolio: null,
      schedule: null,
      notice: { tag: "soon" as const, text: SOON },
    },
    "static:deploy-draft",
    pinR.pin,
    null,
    "unavailable",
  );
}

export const registerStrategies: RouteModule<Env> = (reg) => {
  reg.get("/strategies/summary", summary);
  reg.get("/strategies", strategies);
  reg.get("/strategies/deployments", async (req) => deployments(req));
  reg.get("/strategies/targets", async (req) => targets(req));
  reg.get("/strategies/default", overview);
  reg.get("/strategies/default/parameters", parameters);
  reg.get("/strategies/default/performance", performance);
  reg.get("/strategies/default/runs", async (req) => runs(req));
  reg.get("/strategies/deploy-flow", async (req) => deployFlow(req));
  reg.get("/strategies/default/deploy-draft", async (req) => deployDraft(req));
};
