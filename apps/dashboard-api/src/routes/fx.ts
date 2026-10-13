/**
 * Phase 3 — FX hub (group 12x) and rates reads.
 * twelve-x tables use the twelve-x reader. fx_intraday_observations and
 * macro_series_observations are core. Flags, paper exposure, and directives
 * have no applied table: GET returns a typed empty state; PUT directives
 * returns 503 not_provisioned.
 */

import { buildProvenance, errorResponse } from "../errors";
import { tableRows, twelvexRead, type TableReadEnv } from "../table-read";
import type { RouteCtx, RouteModule } from "./registry";

type Row = Record<string, unknown>;
type Env = TableReadEnv;

/** Documented core series ids (migration 130). Unknown pairs are not guessed. */
export const PAIR_TO_SERIES: Record<string, string> = {
  EURUSD: "FX/EUR",
  GBPUSD: "FX/GBP",
  USDJPY: "FX/JPY",
  USDCAD: "FX/CAD",
  AUDUSD: "FX/AUD",
  USDCHF: "FX/CHF",
  NZDUSD: "FX/NZD",
};

const CURVE_TENORS: { id: string; tenor: string }[] = [
  { id: "DGS2", tenor: "2Y" },
  { id: "DGS5", tenor: "5Y" },
  { id: "DGS10", tenor: "10Y" },
  { id: "DGS30", tenor: "30Y" },
];

const NOT_PROVISIONED = "not provisioned — migration drafted, not applied";

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

function ok(data: unknown, source: string, pin: string | null, asOf: string | null, marks: "stored" | "unavailable" = "stored"): Response {
  return Response.json({
    data,
    as_of: asOf,
    retrieval_pin: pin,
    provenance: buildProvenance({ source, tip_date: asOf, marks }),
  });
}

function normPair(raw: string): string {
  return raw.replace(/[^A-Za-z]/g, "").toUpperCase();
}

function themes(v: unknown): string[] {
  if (Array.isArray(v)) return v.filter((x): x is string => typeof x === "string" && x.length > 0);
  return [];
}

async function tx(env: Env, table: string, query: string): Promise<{ rows: Row[] } | { error: Response }> {
  const res = await twelvexRead(env, { table, query, allowEmpty: true });
  if (res.status !== 200) return { error: res };
  const body = (await res.json()) as { data?: unknown };
  return { rows: Array.isArray(body.data) ? (body.data as Row[]) : [] };
}

async function summary(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const digest = await tx(ctx.env, "fx_daily_digest", "select=*&order=run_date.desc&limit=1");
  if ("error" in digest) return digest.error;
  const ideas = await tx(ctx.env, "fx_trade_ideas_snapshot", "select=pair,run_date&order=run_date.desc&limit=100");
  if ("error" in ideas) return ideas.error;
  const row = digest.rows[0];
  const runDate = row ? str(row.run_date)?.slice(0, 10) ?? null : null;
  const latestIdeas = runDate ? ideas.rows.filter((r) => str(r.run_date)?.slice(0, 10) === runDate) : ideas.rows;
  const pairs = new Set(latestIdeas.map((r) => str(r.pair)).filter((p): p is string => p !== null));
  const lead = row ? str(row.summary) : null;
  return ok(
    {
      desk: "fx",
      run_date: runDate,
      posture: null,
      pairs: { count: pairs.size, note: null },
      ideas: { count: latestIdeas.length, note: null },
      paper_exposure: { gross_usd: null, venue: null },
      session: { name: null, note: null },
      research_flags: { count: null },
      read: lead ? { lead, body: null } : null,
      changes: themes(row?.key_themes),
    },
    "twelvex:fx_daily_digest",
    pinR.pin,
    runDate,
  );
}

function ideaRow(r: Row) {
  return {
    rank: num(r.rank),
    pair: str(r.pair) ?? "",
    bias: str(r.direction) ?? str(r.bias),
    horizon: str(r.timeframe) ?? str(r.horizon),
    invalidation: num(r.invalidation) ?? num(r.stop_price),
    status: str(r.status),
    levels: null as string | null,
    thread: str(r.thesis) ?? str(r.title),
  };
}

async function ideas(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const out = await tx(ctx.env, "fx_trade_ideas_snapshot", "select=*&order=run_date.desc,rank.asc&limit=50");
  if ("error" in out) return out.error;
  const runDate = out.rows.map((r) => str(r.run_date)?.slice(0, 10)).find((d) => d) ?? null;
  const latest = runDate ? out.rows.filter((r) => str(r.run_date)?.slice(0, 10) === runDate) : out.rows;
  return ok(
    { ideas: latest.map(ideaRow).filter((r) => r.pair !== "") },
    "twelvex:fx_trade_ideas_snapshot",
    pinR.pin,
    runDate ?? null,
  );
}

async function ideaDetail(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const want = normPair(ctx.params.pair ?? "");
  const out = await tx(ctx.env, "fx_trade_ideas_snapshot", "select=*&order=run_date.desc,rank.asc&limit=50");
  if ("error" in out) return out.error;
  const row = out.rows.find((r) => normPair(str(r.pair) ?? "") === want);
  return ok(
    {
      pair: want,
      rank: row ? num(row.rank) : null,
      headline: row ? str(row.title) : null,
      rationale: row ? str(row.thesis) : null,
      bias: row ? str(row.direction) : null,
      horizon: row ? str(row.timeframe) : null,
      status: row ? str(row.status) : null,
      invalidation: null,
      entry: null,
      target: null,
      catalyst: row ? str(row.catalyst) : null,
      evidence_note: null,
    },
    "twelvex:fx_trade_ideas_snapshot",
    pinR.pin,
    row ? str(row.run_date)?.slice(0, 10) ?? null : null,
  );
}

async function pairs(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const out = await tx(ctx.env, "fx_trade_ideas_snapshot", "select=pair,direction,run_date&order=run_date.desc&limit=100");
  if ("error" in out) return out.error;
  // rows arrive run_date.desc, so the first non-null run_date is the latest run.
  const runDate = out.rows.map((r) => str(r.run_date)?.slice(0, 10)).find((d) => d) ?? null;
  const seen = new Set<string>();
  const list = [];
  for (const r of out.rows) {
    const pair = str(r.pair);
    if (!pair || seen.has(pair)) continue;
    seen.add(pair);
    list.push({ pair, bid: null, offer: null, day_pct: null, bias: str(r.direction), status: null });
  }
  // marks stay "unavailable": bid/offer/day_pct are hardcoded null, never fetched.
  return ok({ pairs: list }, "twelvex:fx_trade_ideas_snapshot", pinR.pin, runDate, "unavailable");
}

async function pairPath(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const pair = normPair(ctx.params.pair ?? "");
  const series = PAIR_TO_SERIES[pair];
  if (!series) {
    return ok({ pair, session: null, points: [], note: "no core series id for this pair" }, "core:fx_intraday_observations", pinR.pin, null, "unavailable");
  }
  const out = await tableRows(ctx.env, {
    table: "fx_intraday_observations",
    // Newest 500 one-hour Yahoo bars (PK is source, series_id, ts, interval), then
    // back into time order: ascending + limit would return the oldest bars.
    query: `select=ts,close&source=eq.yahoo&series_id=eq.${encodeURIComponent(series)}&interval=eq.1h&order=ts.desc&limit=500`,
    allowEmpty: true,
  });
  if ("error" in out) return out.error;
  const points = [...out.rows].reverse().map((r) => ({ t: str(r.ts) ?? "", v: num(r.close) })).filter((p) => p.t !== "");
  const tip = points.at(-1)?.t.slice(0, 10) ?? null;
  return ok({ pair, session: null, points, note: null }, "core:fx_intraday_observations", pinR.pin, tip);
}

async function levels(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const out = await tx(ctx.env, "fx_trade_ideas_snapshot", "select=pair,run_date&order=run_date.desc&limit=50");
  if ("error" in out) return out.error;
  const runDate = out.rows.map((r) => str(r.run_date)?.slice(0, 10)).find((d) => d) ?? null;
  const rows = out.rows.map((r) => ({
    pair: str(r.pair) ?? "",
    mark: null,
    level: null,
    role: null,
    pips: null,
    provenance: null,
    flag: null,
  })).filter((r) => r.pair !== "");
  // marks stay "unavailable": mark/level/role/pips are hardcoded null, never fetched.
  return ok({ levels: rows }, "twelvex:fx_trade_ideas_snapshot", pinR.pin, runDate, "unavailable");
}

function sessions(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok(
    {
      sessions: [
        { session: "Asia", state: null, note: null },
        { session: "London", state: null, note: null },
        { session: "New York", state: null, note: null },
      ],
    },
    "static-sessions",
    pinR.pin,
    null,
    "unavailable",
  );
}

function flags(req: Request, ctx: RouteCtx<Env>): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok(
    { pair: normPair(ctx.params.pair ?? ""), flagged: null, level: null, text: null, scope_note: NOT_PROVISIONED },
    "draft:fx_flags",
    pinR.pin,
    null,
    "unavailable",
  );
}

function paper(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok(
    { venue: null, gross_usd: null, note: NOT_PROVISIONED, lines: [] },
    "draft:fx_paper_exposure",
    pinR.pin,
    null,
    "unavailable",
  );
}

function directivesGet(req: Request): Response {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok(
    {
      allow_pairs: [],
      deny_pairs: [],
      risk_style: null,
      ignore_sources: [],
      writable: false,
      note: NOT_PROVISIONED,
    },
    "draft:fx_directives",
    pinR.pin,
    null,
    "unavailable",
  );
}

function directivesPut(req: Request): Response {
  const pin = new URL(req.url).searchParams.get("retrieval_pin");
  return errorResponse("not_provisioned", NOT_PROVISIONED, pin, { table: "fx_directives" });
}

async function ratesSummary(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const curve = await ratesCurve(req, ctx);
  if (curve.status !== 200) return curve;
  const body = (await curve.json()) as { data?: { curve?: { yield_pct: number | null }[] }; as_of: string | null };
  const points = body.data?.curve ?? [];
  const marks = points.filter((p) => p.yield_pct !== null).length;
  return ok(
    {
      desk: "rates",
      run_date: body.as_of,
      posture: null,
      watchlist: { names: null, marks_available: points.length ? marks : null },
      theses: null,
      last_run: body.as_of ? { date: body.as_of, note: null } : null,
      budget: { spent_usd: null, cap_usd: null },
      read: null,
      signals: [],
      risks: [],
    },
    "core:macro_series_observations",
    pinR.pin,
    body.as_of,
  );
}

async function ratesCurve(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const ids = [...CURVE_TENORS.map((t) => t.id), "T10Y2Y"].join(",");
  const out = await tableRows(ctx.env, {
    table: "macro_series_observations",
    query: `select=series_id,obs_date,value,unit&source=eq.fred&series_id=in.(${ids})&order=obs_date.desc&limit=80`,
    allowEmpty: true,
  });
  if ("error" in out) return out.error;
  const latest = (id: string): { value: number | null; prev: number | null; date: string | null; unit: string | null } => {
    const rows = out.rows.filter((r) => str(r.series_id) === id);
    return {
      value: rows[0] ? num(rows[0].value) : null,
      prev: rows[1] ? num(rows[1].value) : null,
      date: rows[0] ? str(rows[0].obs_date) : null,
      unit: rows[0] ? str(rows[0].unit) : null,
    };
  };
  const curve = CURVE_TENORS.map((t) => {
    const row = latest(t.id);
    const day = row.value !== null && row.prev !== null ? row.value - row.prev : null;
    return { tenor: t.tenor, yield_pct: row.value, day_change: day };
  });
  const spread = latest("T10Y2Y");
  const toBp = (v: number | null, unit: string | null): number | null => {
    if (v === null) return null;
    if (unit && unit.toLowerCase().includes("bp") && !unit.toLowerCase().includes("percent")) return v;
    return v * 100;
  };
  const spreads = [{
    label: "10Y-2Y",
    bp: toBp(spread.value, spread.unit),
    day_bp: spread.value !== null && spread.prev !== null ? toBp(spread.value - spread.prev, spread.unit) : null,
  }];
  const asOf = CURVE_TENORS.map((t) => latest(t.id).date).filter((d): d is string => d !== null).sort().at(-1) ?? null;
  return ok({ curve, spreads }, "core:macro_series_observations", pinR.pin, asOf?.slice(0, 10) ?? null);
}

async function watchlist(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  return ok({ names: [] }, "core:macro_series_observations", pinR.pin, null, "unavailable");
}

async function ratesTheses(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const out = await tx(ctx.env, "theses", "select=*&limit=200");
  if ("error" in out) return out.error;
  const tagged = out.rows.some((r) => str(r.desk) !== null);
  const rows = tagged ? out.rows.filter((r) => (str(r.desk) ?? "").toLowerCase() === "rates") : out.rows;
  const theses = rows.map((r) => ({
    id: str(r.id) ?? str(r.thesis_id) ?? "",
    name: str(r.name) ?? str(r.title) ?? "",
    state: str(r.state)?.toLowerCase() ?? null,
    vehicles: Array.isArray(r.vehicles) ? r.vehicles.filter((v): v is string => typeof v === "string") : [],
    evidence: str(r.evidence),
    kill_condition: str(r.kill_condition),
    note: str(r.note),
  })).filter((t) => t.id !== "");
  const counts = {
    active: theses.filter((t) => t.state === "active").length,
    watch: theses.filter((t) => t.state === "watch").length,
    exited: theses.filter((t) => t.state === "exited").length,
  };
  return ok({ theses, counts }, "twelvex:theses", pinR.pin, null);
}

export const registerFx: RouteModule<Env> = (reg) => {
  reg.get("/fx/summary", summary);
  reg.get("/fx/pairs", pairs);
  reg.get("/fx/levels", levels);
  reg.get("/fx/sessions", async (req) => sessions(req));
  reg.get("/fx/ideas", ideas);
  reg.get("/fx/ideas/{pair}", ideaDetail);
  reg.get("/fx/pairs/{pair}/path", pairPath);
  reg.get("/fx/flags/{pair}", async (req, ctx) => flags(req, ctx));
  reg.get("/fx/paper-exposure", async (req) => paper(req));
  reg.get("/fx/directives", async (req) => directivesGet(req));
  reg.add("PUT", "/fx/directives", async (req) => directivesPut(req));
  reg.get("/rates/summary", ratesSummary);
  reg.get("/rates/curve", ratesCurve);
  reg.get("/rates/watchlist", watchlist);
  reg.get("/rates/theses", ratesTheses);
};
