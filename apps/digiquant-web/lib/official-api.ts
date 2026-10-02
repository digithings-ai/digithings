/**
 * Browser client for the official digiquant read API (dashboard-api).
 *
 * Canonical env is NEXT_PUBLIC_DASHBOARD_API_URL, the same base the dashboard
 * uses (`apps/dashboard/lib/api-client.ts`). NEXT_PUBLIC_DQ_API_URL is accepted
 * as an alias. Loopback previews without that env call the same-origin
 * `/official-api` proxy (next dev → the local worker). Every other host uses
 * the folded stack mount.
 *
 * Stub envelopes (the worker's secretless doubles), withheld reads, and 502
 * `upstream_empty` are empty. They are never painted as the house book.
 */

import { PIPELINE_STAGES, type StageName } from "@/app/_stages";
import type { RunSnapshot, StageSnapshot } from "@/lib/run-snapshot";

export const PRODUCTION_API_BASE = "https://graph.digithings.ai/dashboard-api";
export const DEV_API_PROXY = "/official-api";

export const HOUSE_BOOK_ROUTES = ["/portfolio", "/brief", "/nav-series", "/allocations", "/performance"] as const;
export const PIPELINE_ROUTE = "/v1/tables/documents";
export const STRATEGY_ROUTE = "/v1/tables/strategy_tearsheets";
export const TAPE_ROUTE = "/benchmarks";

const STUB_NAV = [99.909, 204.04];

export function officialApiBase(hostname?: string): string {
  const env = (process.env.NEXT_PUBLIC_DASHBOARD_API_URL ?? process.env.NEXT_PUBLIC_DQ_API_URL ?? "")
    .trim()
    .replace(/\/+$/, "");
  if (env.length > 0) return env;
  const host = hostname ?? (typeof window !== "undefined" ? window.location.hostname : "");
  if (host === "127.0.0.1" || host === "localhost") return DEV_API_PROXY;
  return PRODUCTION_API_BASE;
}

export interface OfficialFailure {
  ok: false;
  reason: string;
}

export interface OfficialSuccess {
  ok: true;
  body: unknown;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function errorMessage(body: unknown): string | null {
  if (!isRecord(body) || !isRecord(body.error)) return null;
  return typeof body.error.message === "string" ? body.error.message : null;
}

function errorCode(body: unknown): string | null {
  if (!isRecord(body) || !isRecord(body.error)) return null;
  return typeof body.error.code === "string" ? body.error.code : null;
}

/**
 * Secretless worker doubles. These figures must not render as the house book.
 * Withhold the worker double only: NAV tip 99.909 and series tip 204.04.
 * `legacy_estimate` on an older point is a house label, not that fixture.
 */
export function isStubPayload(body: unknown): boolean {
  const text = JSON.stringify(body ?? null);
  if (text.includes("99.909") || text.includes("204.04") || text.includes("204.040")) return true;
  if (text.includes("103.040192") || text.includes("104.44808") || text.includes("3.040191838399986")) return true;
  if (text.includes('"close":500') && text.includes("2026-08-20") && text.includes('"close":515')) return true;
  if (!isRecord(body)) return false;
  const data = isRecord(body.data) ? body.data : body;
  const tip = isRecord(data.nav_tip) ? data.nav_tip : null;
  const nav = tip && typeof tip.nav === "number" ? tip.nav : null;
  if (nav != null && STUB_NAV.some((n) => Math.abs(nav - n) < 1e-6)) return true;
  return false;
}

export function classifyOfficialRead(status: number, body: unknown): OfficialSuccess | OfficialFailure {
  if (status === 0) return { ok: false, reason: "The official API did not respond." };
  const code = errorCode(body);
  const message = errorMessage(body);
  if (status === 502 || code === "upstream_empty" || (message != null && /withheld/i.test(message))) {
    const detail = message && message.length < 180 ? message : "upstream_empty";
    return { ok: false, reason: `The official API withheld this read (${detail}).` };
  }
  if (status === 404 || code === "not_found") {
    return { ok: false, reason: "The official API has not published this read." };
  }
  if (status < 200 || status >= 300) {
    return { ok: false, reason: `The official API withheld this read (${status}).` };
  }
  if (isStubPayload(body)) {
    return { ok: false, reason: "The official API returned a stub envelope, not a house-book read." };
  }
  return { ok: true, body };
}

export async function officialGet(path: string, query?: Record<string, string>): Promise<OfficialSuccess | OfficialFailure> {
  const params = new URLSearchParams();
  if (query) {
    for (const [key, value] of Object.entries(query)) params.set(key, value);
  }
  const qs = params.toString();
  const url = `${officialApiBase()}${path}${qs.length > 0 ? `?${qs}` : ""}`;
  try {
    const res = await fetch(url);
    const body: unknown = await res.json().catch(() => null);
    return classifyOfficialRead(res.status, body);
  } catch {
    return { ok: false, reason: "The official API did not respond." };
  }
}

export interface OfficialPosition {
  ticker: string;
  weightPct: number | null;
  currentPrice: number | null;
  entryPrice: number | null;
  dayChangePct: number | null;
  unrealizedPnlPct: number | null;
  cash: boolean;
}

export interface OfficialHouseBook {
  asOf: string | null;
  positions: OfficialPosition[];
  nav: { date: string; nav: number; dayReturnPct: number | null; contract: string | null }[];
  sinceInceptionPct: number | null;
  dayReturnPct: number | null;
  excessReturnPct: number | null;
  benchmarkTicker: string | null;
  priceAsOfDate: string | null;
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function dataOf(body: unknown): Record<string, unknown> | null {
  if (!isRecord(body)) return null;
  return isRecord(body.data) ? body.data : null;
}

/** Map accepted catalog payloads. Caller must already have rejected stubs. */
export function houseBookFromPayloads(payloads: {
  portfolio: unknown;
  brief: unknown;
  nav: unknown;
  allocations: unknown;
  performance: unknown;
}): OfficialHouseBook | null {
  const portfolio = dataOf(payloads.portfolio);
  const brief = dataOf(payloads.brief);
  const nav = dataOf(payloads.nav);
  const allocations = dataOf(payloads.allocations);
  const performance = dataOf(payloads.performance);
  if (!portfolio || !brief || !nav) return null;

  const marks = new Map<string, { price: number | null; entry: number | null; unrealized: number | null }>();
  if (allocations && Array.isArray(allocations.rows)) {
    for (const row of allocations.rows) {
      if (!isRecord(row) || typeof row.ticker !== "string") continue;
      marks.set(row.ticker, {
        price: num(row.current_price),
        entry: num(row.entry_price),
        unrealized: num(row.unrealized_pct),
      });
    }
  }

  const positions: OfficialPosition[] = [];
  if (Array.isArray(portfolio.positions)) {
    for (const row of portfolio.positions) {
      if (!isRecord(row) || typeof row.ticker !== "string") continue;
      const mark = marks.get(row.ticker);
      positions.push({
        ticker: row.ticker,
        weightPct: num(row.weight_pct),
        currentPrice: mark?.price ?? null,
        entryPrice: mark?.entry ?? null,
        dayChangePct: null,
        unrealizedPnlPct: mark?.unrealized ?? null,
        cash: row.is_cash === true || row.ticker.trim().toUpperCase() === "CASH",
      });
    }
  }

  const points: OfficialHouseBook["nav"] = [];
  if (Array.isArray(nav.points)) {
    for (const row of nav.points) {
      if (!isRecord(row) || typeof row.date !== "string") continue;
      const value = num(row.nav);
      if (value == null) continue;
      points.push({
        date: row.date,
        nav: value,
        dayReturnPct: num(row.day_return_pct),
        contract: typeof row.contract === "string" ? row.contract : null,
      });
    }
  }

  const perf = performance && isRecord(performance.metrics) ? performance.metrics : null;
  const bench = performance && isRecord(performance.benchmark) ? performance.benchmark : null;
  const tip = isRecord(brief.nav_tip) ? brief.nav_tip : null;

  return {
    asOf: typeof portfolio.book_as_of === "string" ? portfolio.book_as_of : null,
    positions,
    nav: points,
    sinceInceptionPct: num(brief.since_inception_pct),
    dayReturnPct: num(brief.day_return_pct),
    excessReturnPct: perf ? num(perf.excess_return_pct) : null,
    benchmarkTicker: bench && typeof bench.ticker === "string" ? bench.ticker : null,
    priceAsOfDate: tip && typeof tip.date === "string" ? tip.date : null,
  };
}

const RESEARCH_PREFIXES = ["alt-", "inst-", "sector-"];
const ASSET_CLASSES = new Set(["bonds", "commodities", "forex", "crypto", "equity", "international"]);
const TITLED = new Set<StageName>(["Inputs", "Research", "Synthesis"]);
const SECRET = /eyJ[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{10,}|[A-Za-z0-9]{32,}/;

/** Mirror of scripts/capture_latest_run.py stage_for_key. */
export function stageForDocumentKey(key: string): StageName | null {
  const k = key.toLowerCase();
  if (k === "attention-plan" || k === "inputs") return "Inputs";
  if (k === "bias-row" || k === "digest" || k === "digest-delta") return "Synthesis";
  if (k.startsWith("analyst/") || k.startsWith("deliberation/") || k.startsWith("thesis/")) return "Selection";
  if (
    k === "opportunity-screener" ||
    k === "opportunity-screener.json" ||
    k === "pm-direction-memo" ||
    k === "pm-rebalance" ||
    k === "risk-debate"
  ) {
    return "Selection";
  }
  if (k.startsWith("commit-run/")) return "Decision";
  if (k === "beliefs") return "Learning";
  if (k.startsWith("document-deltas/")) return "Research";
  if (RESEARCH_PREFIXES.some((p) => k.startsWith(p)) || k === "macro" || ASSET_CLASSES.has(k)) return "Research";
  return null;
}

function safeTitle(title: unknown): string | null {
  if (typeof title !== "string") return null;
  const t = title.split(/\s+/).join(" ").trim();
  if (!t || t.includes("%") || SECRET.test(t)) return null;
  return t.slice(0, 80);
}

/** Latest-run snapshot from documents rows. Empty rows are not a fabricated run. */
export function runFromDocuments(rows: unknown[]): RunSnapshot | null {
  const docs = rows.filter(isRecord).filter((r) => typeof r.document_key === "string" && typeof r.date === "string");
  if (docs.length === 0) return null;
  const dates = [...new Set(docs.map((r) => String(r.date)))].sort();
  const runDate = dates[dates.length - 1];
  const day = docs.filter((r) => r.date === runDate);
  const counts = new Map<string, number>();
  for (const row of day) {
    if (typeof row.run_type !== "string" || row.run_type.length === 0) continue;
    counts.set(row.run_type, (counts.get(row.run_type) ?? 0) + 1);
  }
  const runType = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
  const byStage = new Map<StageName, Record<string, unknown>[]>(PIPELINE_STAGES.map((name) => [name, []]));
  for (const row of day) {
    const stage = stageForDocumentKey(String(row.document_key));
    if (stage) byStage.get(stage)?.push(row);
  }
  const stages: StageSnapshot[] = PIPELINE_STAGES.map((name) => {
    const group = byStage.get(name) ?? [];
    const stage: StageSnapshot = {
      name,
      status: group.length > 0 ? "recorded" : "not-recorded",
      documentCount: group.length,
    };
    if (TITLED.has(name)) {
      stage.titles = [...new Set(group.map((d) => safeTitle(d.title)).filter((t): t is string => t != null))].sort().slice(0, 6);
    }
    return stage;
  });
  return { runDate, runType, stages };
}

export interface TapeSeries {
  symbol: string;
  points: { date: string; price: number }[];
}

/** Benchmark closes from GET /benchmarks. A stub series is dropped entirely. */
export function tapeFromBenchmarks(body: unknown): TapeSeries[] | null {
  if (isStubPayload(body)) return null;
  const data = dataOf(body);
  if (!data || !isRecord(data.series)) return null;
  const out: TapeSeries[] = [];
  for (const [symbol, rows] of Object.entries(data.series)) {
    if (!Array.isArray(rows)) continue;
    const points = rows
      .map((row) => {
        if (!isRecord(row) || typeof row.date !== "string") return null;
        const price = num(row.close);
        return price != null && price > 0 ? { date: row.date, price } : null;
      })
      .filter((p): p is { date: string; price: number } => p != null);
    if (points.length > 0) out.push({ symbol, points });
  }
  return out;
}
