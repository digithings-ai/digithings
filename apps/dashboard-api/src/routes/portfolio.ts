/**
 * Phase 1 — baseline portfolio routes. Each read is an enveloped tableRead
 * (or a reshape of one). Missing numbers stay null. Empty lists are success.
 */

import { buildProvenance, errorResponse, type Provenance } from "../errors";
import { HOUSE_WORKSPACE_ID } from "../supabase";
import { tableRows, type TableReadEnv } from "../table-read";
import { maxThesisDate, rowsAtDate, thesisShape } from "../thesis-shape";
import type { RouteCtx, RouteModule } from "./registry";

type Row = Record<string, unknown>;
type Env = TableReadEnv;

/** Versioned sleeve codes over instrument type/class. Unknown codes stay null. */
export const INSTRUMENT_SLEEVE_MAP = {
  version: "2026-10-02",
  byCode: {
    equity: "Equity",
    etf: "ETF",
    cash: "Cash",
    fx: "FX",
    rates: "Rates",
  } as Record<string, string>,
};

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

function asOfParam(req: Request, pin: string | null): { asOf: string | null } | { error: Response } {
  const asOf = new URL(req.url).searchParams.get("asOf");
  if (asOf === null) return { asOf: null };
  if (!/^\d{4}-\d{2}-\d{2}$/.test(asOf)) {
    return { error: errorResponse("bad_request", "asOf must be a calendar date YYYY-MM-DD", pin, { asOf }) };
  }
  return { asOf };
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

function maxDate(rows: Row[], field: string): string | null {
  let best: string | null = null;
  for (const r of rows) {
    const v = str(r[field]);
    if (v && (best === null || v > best)) best = v;
  }
  return best;
}

function sleeveFor(instrument: Row | undefined): string | null {
  if (!instrument) return null;
  const explicit = str(instrument.sleeve);
  if (explicit) return explicit;
  const code = (str(instrument.instrument_type) ?? str(instrument.asset_class) ?? "").toLowerCase();
  return INSTRUMENT_SLEEVE_MAP.byCode[code] ?? null;
}

async function enriched(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const asOfR = asOfParam(req, pinR.pin);
  if ("error" in asOfR) return asOfR.error;
  const positions = await read(
    ctx.env,
    "positions",
    `select=*&workspace_id=eq.${HOUSE_WORKSPACE_ID}&order=date.desc&limit=5000`,
  );
  if ("error" in positions) return positions.error;
  const instruments = await read(ctx.env, "instruments", "select=*&limit=5000");
  if ("error" in instruments) return instruments.error;
  const dated = positions.rows.filter((r) => str(r.date) !== null && (asOfR.asOf === null || (str(r.date) ?? "") <= asOfR.asOf));
  const bookDate = maxDate(dated, "date");
  const book = bookDate === null ? [] : dated.filter((r) => str(r.date) === bookDate);
  const byTicker = new Map<string, Row>();
  for (const ins of instruments.rows) {
    const t = str(ins.ticker) ?? str(ins.symbol);
    if (t) byTicker.set(t.toUpperCase(), ins);
  }
  const rows = book.map((r) => {
    const ticker = str(r.ticker) ?? "";
    const ins = byTicker.get(ticker.toUpperCase());
    const shares = num(r.shares) ?? num(r.quantity);
    const price = num(r.current_price);
    const value = shares !== null && price !== null ? shares * price : null;
    return {
      ticker,
      name: ins ? str(ins.name) : null,
      sleeve: sleeveFor(ins),
      scaled_weight_pct: num(r.weight_pct) ?? num(r.scaled_weight_pct),
      entry_price: num(r.entry_price),
      current_price: price,
      unrealized_pct: num(r.unrealized_pnl_pct) ?? num(r.since_entry_return_pct),
      shares,
      value,
      day_return_pct: num(r.day_return_pct),
      thesis_id: str(r.thesis_id),
      is_cash: r.is_cash === true || ticker.toUpperCase() === "CASH",
    };
  });
  const groups = new Map<string, { names: number; weights: number[]; complete: boolean }>();
  for (const row of rows) {
    if (row.is_cash) continue;
    const key = row.sleeve ?? "Unassigned";
    const g = groups.get(key) ?? { names: 0, weights: [], complete: true };
    g.names += 1;
    if (row.scaled_weight_pct === null) g.complete = false;
    else g.weights.push(row.scaled_weight_pct);
    groups.set(key, g);
  }
  const sleeves = [...groups.entries()].map(([sleeve, g]) => ({
    sleeve,
    names: g.names,
    weight_pct: g.complete ? g.weights.reduce((a, b) => a + b, 0) : null,
  }));
  const values = rows.map((r) => r.value);
  const bookValue = values.length > 0 && values.every((v) => v !== null) ? values.reduce((a, b) => a + (b ?? 0), 0) : null;
  const cash = rows.find((r) => r.is_cash);
  return ok(
    { book_as_of: bookDate, rows, cash_value: cash?.value ?? null, book_value: bookValue, sleeves },
    "core:positions+instruments",
    pinR.pin,
    bookDate,
  );
}

/**
 * The house thesis book. `theses` keeps one row per thesis per business `date`,
 * so an unfiltered read repeats every thesis across dates and inflates every
 * count in the envelope. Only the newest date is the current book.
 *
 * `date` is sent as `as_of`; `updated_at` is a write timestamp, not a run, and a
 * pane that ages by it looks current after a no-op edit. Same mapper, same
 * newest-date rule as /rates/theses.
 */
async function theses(req: Request, ctx: RouteCtx<Env>, onlySignals: boolean): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const rows = await read(ctx.env, "theses", "select=*&order=date.desc&limit=500");
  if ("error" in rows) return rows.error;
  const vehicles = await read(ctx.env, "thesis_vehicles", "select=*&order=date.desc&limit=2000");
  if ("error" in vehicles) return vehicles.error;
  const filtered = onlySignals ? rows.rows.filter((r) => r.needs_resolution === true) : rows.rows;
  const tip = maxThesisDate(filtered);
  // Vehicles are dated too. Holding them at every date would show each thesis
  // every ticker it has ever carried.
  return ok(
    thesisShape(rowsAtDate(filtered, tip), rowsAtDate(vehicles.rows, tip)),
    "core:theses",
    pinR.pin,
    tip,
  );
}

async function attribution(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const out = await read(ctx.env, "position_attribution", "select=*&order=as_of.desc&limit=500");
  if ("error" in out) return out.error;
  const start = maxDate(out.rows, "window_start") ?? maxDate(out.rows, "start");
  const end = maxDate(out.rows, "window_end") ?? maxDate(out.rows, "end") ?? maxDate(out.rows, "as_of");
  const names = out.rows.map((r) => ({
    ticker: str(r.ticker) ?? "",
    sleeve: str(r.sleeve),
    contribution_bp: num(r.contribution_bp),
  })).filter((r) => r.ticker !== "");
  const sleeveMap = new Map<string, { vals: number[]; complete: boolean }>();
  for (const n of names) {
    const key = n.sleeve ?? "Unassigned";
    const g = sleeveMap.get(key) ?? { vals: [], complete: true };
    if (n.contribution_bp === null) g.complete = false;
    else g.vals.push(n.contribution_bp);
    sleeveMap.set(key, g);
  }
  const sleeves = [...sleeveMap.entries()].map(([sleeve, g]) => ({
    sleeve,
    contribution_bp: g.complete && g.vals.length > 0 ? g.vals.reduce((a, b) => a + b, 0) : null,
  }));
  return ok(
    { window: { start: start?.slice(0, 10) ?? null, end: end?.slice(0, 10) ?? null }, sleeves, names },
    "core:position_attribution",
    pinR.pin,
    end ? end.slice(0, 10) : null,
  );
}

async function cash(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const periods = await read(ctx.env, "accounting_periods", "select=*&order=period_end.desc&limit=200");
  if ("error" in periods) return periods.error;
  const events = await read(
    ctx.env,
    "position_events",
    `select=*&workspace_id=eq.${HOUSE_WORKSPACE_ID}&order=date.desc&limit=200`,
  );
  if ("error" in events) return events.error;
  const fromPeriods = periods.rows.map((r) => ({
    date: (str(r.period_end) ?? str(r.date) ?? "").slice(0, 10),
    kind: str(r.kind) ?? "period",
    amount: num(r.cash_flow) ?? num(r.amount),
    balance: num(r.cash_balance) ?? num(r.balance),
  })).filter((e) => e.date !== "");
  const fromEvents = events.rows
    .filter((r) => {
      const kind = (str(r.type) ?? str(r.kind) ?? "").toLowerCase();
      return kind.includes("cash") || num(r.cash_amount) !== null;
    })
    .map((r) => ({
      date: (str(r.date) ?? "").slice(0, 10),
      kind: str(r.type) ?? str(r.kind) ?? "cash",
      amount: num(r.cash_amount) ?? num(r.amount),
      balance: num(r.balance),
    }))
    .filter((e) => e.date !== "");
  const entries = [...fromPeriods, ...fromEvents];
  return ok({ entries }, "core:accounting_periods+position_events", pinR.pin, maxDate(entries.map((e) => ({ date: e.date })), "date"));
}

function daySpan(a: string | null, b: string | null): number | null {
  if (!a || !b) return null;
  const ms = Date.parse(b) - Date.parse(a);
  if (!Number.isFinite(ms)) return null;
  return Math.round(ms / 86400000);
}

async function drawdown(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const out = await read(ctx.env, "public_accounting_nav_history", "select=date,nav&order=date.asc&limit=5000");
  if ("error" in out) return out.error;
  const points = out.rows
    .map((r) => ({ t: (str(r.date) ?? "").slice(0, 10), nav: num(r.nav) }))
    .filter((p) => p.t !== "" && p.nav !== null && p.nav > 0) as { t: string; nav: number }[];
  let peak = points[0]?.nav ?? null;
  let peakDate = points[0]?.t ?? null;
  let trough = peak;
  let troughDate = peakDate;
  let open = false;
  const series: { t: string; v: number | null }[] = [];
  const episodes: { depth_pct: number | null; start: string | null; trough: string | null; recovery: string | null; days: number | null }[] = [];
  for (const p of points) {
    if (peak === null || p.nav >= peak) {
      if (open && trough !== null && peak !== null) {
        episodes.push({
          depth_pct: (trough / peak - 1) * 100,
          start: peakDate,
          trough: troughDate,
          recovery: p.t,
          days: daySpan(peakDate, p.t),
        });
      }
      peak = p.nav;
      peakDate = p.t;
      trough = p.nav;
      troughDate = p.t;
      open = false;
    } else {
      open = true;
      if (trough === null || p.nav < trough) {
        trough = p.nav;
        troughDate = p.t;
      }
    }
    series.push({ t: p.t, v: peak ? (p.nav / peak - 1) * 100 : null });
  }
  const depths = series.map((s) => s.v).filter((v): v is number => v !== null);
  const max = depths.length ? Math.min(...depths) : null;
  const maxIdx = max === null ? -1 : series.findIndex((s) => s.v === max);
  return ok(
    {
      max_pct: max,
      current_pct: series.at(-1)?.v ?? null,
      peak_date: maxIdx >= 0 ? series.slice(0, maxIdx + 1).reduce((a, s) => (s.v === 0 ? s.t : a), series[0]?.t ?? null) : null,
      trough_date: maxIdx >= 0 ? series[maxIdx]?.t ?? null : null,
      series,
      episodes,
    },
    "core:public_accounting_nav_history",
    pinR.pin,
    points.at(-1)?.t ?? null,
  );
}

async function decision(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const out = await read(ctx.env, "decision_log", "select=*&order=created_at.desc&limit=20");
  if ("error" in out) return out.error;
  const row = out.rows.find((r) => str(r.lead) ?? str(r.title) ?? str(r.summary) ?? str(r.decision));
  const lead = row ? str(row.lead) ?? str(row.title) ?? str(row.summary) ?? str(row.decision) : null;
  const runDate = row ? (str(row.run_date) ?? str(row.created_at)) : null;
  return ok(
    { decision: lead ? { lead, body: row ? str(row.body) ?? str(row.note) : null, run_date: runDate ? runDate.slice(0, 10) : null } : null },
    "core:decision_log",
    pinR.pin,
    runDate ? runDate.slice(0, 10) : null,
  );
}

async function risks(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const out = await read(ctx.env, "documents", "select=*&limit=200");
  if ("error" in out) return out.error;
  const items = out.rows
    .filter((r) => (str(r.kind) ?? str(r.doc_type) ?? str(r.type) ?? "").toLowerCase().includes("risk"))
    .map((r) => str(r.body) ?? str(r.title) ?? str(r.summary))
    .filter((s): s is string => s !== null);
  return ok({ risks: items }, "core:documents", pinR.pin, maxDate(out.rows, "as_of")?.slice(0, 10) ?? null);
}

/**
 * Per-ticker dossier drawer data.
 *
 * The thesis and its vehicle mapping are read as **one dated book**, the same way
 * `/theses` (below) and `/rates/theses` read theirs. Both tables are dated on the
 * key they share: `theses` is one row per `(date, thesis_id)` under
 * `UNIQUE(date, thesis_id)`, while `thesis_vehicles` is one row per
 * `(date, thesis_id, ticker)` — so a thesis carrying several vehicles has several
 * rows at one date, and the vehicle side is a `Set` of thesis ids rather than a
 * single id. `maxThesisDate` picks the business date the book was struck on and
 * `rowsAtDate` narrows both sides to it.
 * (`digiquant/supabase/migrations/001_initial_schema.sql:58-69`,
 * `024_thesis_deliberation_first_class.sql:18-34`)
 *
 * `order=date.desc` is what makes the tip derivable under a row cap:
 * `maxThesisDate` maxima over the page PostgREST returned, so an unordered `limit`
 * could drop the newest date away. `idx_theses_date ON theses(date DESC)` backs it.
 * This route still issues exactly five reads; the fix adds none.
 *
 * Three consequences worth keeping:
 * - The vehicle join is on `thesis_id`, never the row `id`. `id` is a uuid
 *   (`gen_random_uuid()`), so joining on it matches nothing; `thesis_id` is the
 *   stable business key both tables share.
 * - `thesis_vehicles` has `FOREIGN KEY (date, thesis_id) REFERENCES theses (date,
 *   thesis_id) ON DELETE CASCADE`, so every vehicle at date D has a thesis at date
 *   D: narrowing to the tip cannot cross-join one to another date's thesis. It
 *   says nothing about vehicles *existing* at the tip — vehicle writes are
 *   best-effort enrichment that never blocks the book — so on such a day the drawer
 *   correctly withholds instead of showing a stale thesis.
 * - `theses` has no `ticker` column (the ticker-ish column is `vehicle`), so the
 *   `str(r.ticker)` arm of the resolver cannot fire against real rows; in practice
 *   resolution rides `thesis_vehicles`.
 *
 * `date` is the only age available: there is no separate business-date column, and
 * `updated_at` is a row-write timestamp — a no-op edit on a stale-date row makes
 * that row look like the newest book, so a pane that aged by it would read current
 * while showing stale content. The thesis date is deliberately not surfaced:
 * `as_of` stays `positions`-derived, exactly as it was before this fix.
 */
async function dossier(req: Request, ctx: RouteCtx<Env>): Promise<Response> {
  const pinR = pinOf(req);
  if ("error" in pinR) return pinR.error;
  const ticker = (ctx.params.ticker ?? "").trim();
  if (!/^[A-Za-z0-9._-]{1,32}$/.test(ticker)) {
    return errorResponse("bad_request", "ticker must be 1–32 letters, digits, dot, underscore, or hyphen", pinR.pin, { ticker });
  }
  const key = ticker.toUpperCase();
  const [thesesOut, vehicles, events, docs, positions] = await Promise.all([
    read(ctx.env, "theses", "select=*&order=date.desc&limit=500"),
    read(ctx.env, "thesis_vehicles", "select=*&order=date.desc&limit=2000"),
    read(ctx.env, "position_events", `select=*&workspace_id=eq.${HOUSE_WORKSPACE_ID}&order=date.desc&limit=200`),
    read(ctx.env, "documents", "select=*&limit=200"),
    read(ctx.env, "positions", `select=*&workspace_id=eq.${HOUSE_WORKSPACE_ID}&order=date.desc&limit=500`),
  ]);
  if ("error" in thesesOut) return thesesOut.error;
  if ("error" in vehicles) return vehicles.error;
  if ("error" in events) return events.error;
  if ("error" in docs) return docs.error;
  if ("error" in positions) return positions.error;
  const tip = maxThesisDate(thesesOut.rows);
  const book = rowsAtDate(thesesOut.rows, tip);
  const vehicleIds = new Set(
    rowsAtDate(vehicles.rows, tip)
      .filter((r) => (str(r.ticker) ?? str(r.vehicle) ?? "").toUpperCase() === key)
      .map((r) => str(r.thesis_id))
      .filter((id): id is string => id !== null),
  );
  const thesis = book.find((r) => vehicleIds.has(str(r.thesis_id) ?? str(r.id) ?? "") || (str(r.ticker) ?? "").toUpperCase() === key);
  const pos = positions.rows.find((r) => (str(r.ticker) ?? "").toUpperCase() === key);
  const ev = events.rows.filter((r) => (str(r.ticker) ?? "").toUpperCase() === key).map((r) => ({
    date: str(r.date)?.slice(0, 10) ?? null,
    type: str(r.type) ?? str(r.kind),
  }));
  const documents = docs.rows
    .filter((r) => (str(r.ticker) ?? "").toUpperCase() === key || (str(r.title) ?? "").toUpperCase().includes(key))
    .map((r) => ({ title: str(r.title) }));
  return ok(
    {
      ticker: key,
      thesis: thesis
        ? { id: str(thesis.id) ?? str(thesis.thesis_id), name: str(thesis.name) ?? str(thesis.title), state: str(thesis.state) ?? str(thesis.status) }
        : null,
      vehicles: [...vehicleIds],
      pnl: { unrealized_pct: pos ? num(pos.unrealized_pnl_pct) ?? num(pos.since_entry_return_pct) : null },
      stop: pos ? num(pos.stop) ?? num(pos.stop_price) : null,
      target: pos ? num(pos.target) ?? num(pos.target_price) : null,
      events: ev,
      documents,
    },
    "core:dossier",
    pinR.pin,
    pos ? str(pos.date)?.slice(0, 10) ?? null : null,
  );
}

export const registerPortfolio: RouteModule<Env> = (reg) => {
  reg.get("/allocations/enriched", enriched);
  reg.get("/attribution", attribution);
  reg.get("/theses", (req, ctx) => theses(req, ctx, false));
  reg.get("/theses/signals", (req, ctx) => theses(req, ctx, true));
  reg.get("/ledger/cash", cash);
  reg.get("/performance/drawdown", drawdown);
  reg.get("/brief/decision", decision);
  reg.get("/brief/risks", risks);
  reg.get("/dossier/{ticker}", dossier);
};
