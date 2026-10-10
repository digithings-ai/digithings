/**
 * Official digiquant reads for the landing band.
 *
 * The browser calls the dashboard API (same routes the terminal uses).
 * A stub envelope, a withheld read, or a transport failure is an empty
 * result. Nothing here invents a return.
 */

export const PRODUCTION_API_BASE = "https://graph.digithings.ai/dashboard-api";
export const DEV_API_PROXY = "/official-api";

const STUB_MARKERS = ["legacy_estimate", "99.909", "204.04", "204.040", "103.040192", "104.44808"];

export function officialApiBase(hostname?: string): string {
  const env = (process.env.NEXT_PUBLIC_DASHBOARD_API_URL ?? process.env.NEXT_PUBLIC_DQ_API_URL ?? "")
    .trim()
    .replace(/\/+$/, "");
  if (env.length > 0) return env;
  const host = hostname ?? (typeof window !== "undefined" ? window.location.hostname : "");
  if (host === "127.0.0.1" || host === "localhost") return DEV_API_PROXY;
  return PRODUCTION_API_BASE;
}

export function isStubPayload(body: unknown): boolean {
  const text = JSON.stringify(body ?? null);
  return STUB_MARKERS.some((marker) => text.includes(marker));
}

export interface OfficialFailure {
  ok: false;
  reason: string;
}

export interface OfficialSuccess {
  ok: true;
  body: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function errorCode(body: unknown): string | null {
  if (!isRecord(body) || !isRecord(body.error)) return null;
  return typeof body.error.code === "string" ? body.error.code : null;
}

export function classifyOfficialRead(status: number, body: unknown): OfficialSuccess | OfficialFailure {
  if (status === 0) return { ok: false, reason: "The official API did not respond." };
  const code = errorCode(body);
  if (status === 403 || code === "forbidden") {
    return { ok: false, reason: "The official API has not published this read." };
  }
  if (status === 404 || code === "not_found") {
    return { ok: false, reason: "The official API has not published this read." };
  }
  if (status === 502 || code === "upstream_empty") {
    return { ok: false, reason: "The official API withheld this read." };
  }
  if (status < 200 || status >= 300) {
    return { ok: false, reason: "The official API withheld this read." };
  }
  if (isStubPayload(body)) {
    return { ok: false, reason: "The official API returned a stub envelope, not a house-book read." };
  }
  return { ok: true, body };
}

export async function officialGet(
  path: string,
  query?: Record<string, string>,
): Promise<OfficialSuccess | OfficialFailure> {
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

function dataOf(body: unknown): Record<string, unknown> | null {
  if (!isRecord(body)) return null;
  return isRecord(body.data) ? body.data : body;
}

function num(value: unknown): number | null {
  const n = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(n) ? n : null;
}

export interface NavPoint {
  date: string;
  nav: number;
}

export interface PricePoint {
  date: string;
  price: number;
}

/** Portfolio index from GET /performance. Empty when the read is not a real book. */
export function portfolioFromPerformance(body: unknown): NavPoint[] {
  const data = dataOf(body);
  const nav = data && isRecord(data.nav) ? data.nav : null;
  const points = nav && Array.isArray(nav.points) ? nav.points : [];
  const out: NavPoint[] = [];
  for (const row of points) {
    if (!isRecord(row) || typeof row.date !== "string") continue;
    const value = num(row.index) ?? num(row.nav);
    if (value == null || value <= 0) continue;
    out.push({ date: row.date.slice(0, 10), nav: value });
  }
  return out;
}

/** One benchmark leg from GET /benchmarks. */
export function benchmarkFromBenchmarks(body: unknown, ticker: string): PricePoint[] {
  const data = dataOf(body);
  const series = data && isRecord(data.series) ? data.series[ticker] : null;
  if (!Array.isArray(series)) return [];
  const out: PricePoint[] = [];
  for (const row of series) {
    if (!isRecord(row) || typeof row.date !== "string") continue;
    const price = num(row.close) ?? num(row.price);
    if (price == null || price <= 0) continue;
    out.push({ date: row.date.slice(0, 10), price });
  }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}

export interface CatalogStrategy {
  id: string;
  name: string;
  symbol: string | null;
}

export function strategiesFromCatalog(body: unknown): CatalogStrategy[] {
  const data = dataOf(body);
  const rows = data && Array.isArray(data.strategies) ? data.strategies : [];
  const out: CatalogStrategy[] = [];
  for (const row of rows) {
    if (!isRecord(row) || typeof row.id !== "string" || row.id.length === 0) continue;
    out.push({
      id: row.id,
      name: typeof row.name === "string" && row.name.length > 0 ? row.name : row.id,
      symbol: typeof row.universe === "string" ? row.universe : null,
    });
  }
  return out;
}

export interface TearsheetCardRead {
  id: string;
  name: string;
  symbol: string | null;
  kind: string | null;
  netProfitPct: number | null;
  maxDrawdownPct: number | null;
  profitFactor: number | null;
  winRatePct: number | null;
  totalTrades: number | null;
  periodStart: string | null;
  periodEnd: string | null;
  vsLumpPct: number | null;
  allocatedPct: number | null;
}

/** Card fields from GET /strategies/default/performance. Nulls stay null. */
export function cardFromPerformance(body: unknown): TearsheetCardRead | null {
  const data = dataOf(body);
  const card = data && isRecord(data.card) ? data.card : null;
  if (!card || typeof card.id !== "string" || card.id.length === 0) return null;
  return {
    id: card.id,
    name: typeof card.name === "string" && card.name.length > 0 ? card.name : card.id,
    symbol: typeof card.symbol === "string" ? card.symbol : null,
    kind: typeof card.kind === "string" ? card.kind : null,
    netProfitPct: num(card.net_profit_pct),
    maxDrawdownPct: num(card.max_drawdown_pct),
    profitFactor: num(card.profit_factor),
    winRatePct: num(card.win_rate_pct),
    totalTrades: num(card.total_trades),
    periodStart: typeof card.period_start === "string" ? card.period_start : null,
    periodEnd: typeof card.period_end === "string" ? card.period_end : null,
    vsLumpPct: num(card.vs_lump_pct),
    allocatedPct: num(card.allocated_pct),
  };
}
