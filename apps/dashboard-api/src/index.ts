/**
 * dashboard-api — central read-only dashboard API (Cloudflare Worker).
 *
 * Contract: apps/dashboard-api/CONTRACT.md. All digi product names stay
 * lowercase. No auth/session changes, no digikey/ code, no
 * digiquant/brokers/ code, no live-trading paths, no new public
 * hostname/routes on any domain (human gate).
 *
 * Slice 2 scaffold: router + error envelope + provenance builder +
 * GET /healthz + GET /portfolio (with the book_as_of gate folded in per
 * CONTRACT.md section 0 — there is no standalone /book-date route).
 */

export const HOUSE_WORKSPACE_ID = "6b753576-ced9-5319-9bfa-c5d0aacd9319" as const;

export interface Env {
  SUPABASE_URL?: string;
  SUPABASE_SERVICE_ROLE_KEY?: string;
}

export type ErrorCode = "bad_request" | "not_found" | "upstream_empty" | "internal";

export interface Provenance {
  source: string;
  tip_date: string | null;
  contract: "finalized_accounting" | "legacy_estimate" | null;
  seam: boolean;
  marks: "stored" | "market_api" | "unavailable";
}

const ERROR_STATUS: Record<ErrorCode, number> = {
  bad_request: 400,
  not_found: 404,
  upstream_empty: 502,
  internal: 500,
};

/** Contract section 2 error envelope — the only failure shape. */
export function errorResponse(
  code: ErrorCode,
  message: string,
  retrievalPin: string | null,
  details: Record<string, unknown> = {},
): Response {
  return Response.json(
    { error: { code, message, details, retrieval_pin: retrievalPin } },
    { status: ERROR_STATUS[code] },
  );
}

/** Contract section 1 provenance object — every success carries one. */
export function buildProvenance(partial: Partial<Provenance> & Pick<Provenance, "source">): Provenance {
  return {
    tip_date: null,
    contract: null,
    seam: false,
    marks: "unavailable",
    ...partial,
  };
}

export interface CommonParams {
  asOf: string | null;
  retrievalPin: string | null;
}

const AS_OF_RE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Contract section 1 common query params. Throws a Response (the error
 * envelope) on malformed input so handlers can `catch (e) return e`.
 */
export function parseCommonParams(url: URL): CommonParams {
  const retrievalPin = url.searchParams.get("retrieval_pin");
  if (retrievalPin !== null && retrievalPin.length > 128) {
    throw errorResponse("bad_request", "retrieval_pin exceeds 128 characters", null, {
      max_length: 128,
    });
  }
  const asOf = url.searchParams.get("asOf");
  if (asOf !== null) {
    const d = new Date(`${asOf}T00:00:00Z`);
    if (!AS_OF_RE.test(asOf) || Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== asOf) {
      throw errorResponse("bad_request", "asOf must be a calendar date YYYY-MM-DD", retrievalPin, {
        asOf,
      });
    }
  }
  return { asOf, retrievalPin };
}

function normalizePath(pathname: string): string {
  if (pathname.length > 1 && pathname.endsWith("/")) return pathname.slice(0, -1);
  return pathname || "/";
}

interface BookFetch {
  getJson(path: string): Promise<unknown>;
}

function restClient(env: Env, retrievalPin: string | null): BookFetch {
  const base = (env.SUPABASE_URL ?? "").replace(/\/$/, "");
  const key = env.SUPABASE_SERVICE_ROLE_KEY ?? "";
  return {
    async getJson(path: string): Promise<unknown> {
      const headers: Record<string, string> = {
        apikey: key,
        Authorization: `Bearer ${key}`,
      };
      // Contract section 4: forward the pin unchanged so traces join.
      if (retrievalPin !== null) headers["X-Retrieval-Pin"] = retrievalPin;
      const res = await fetch(`${base}/rest/v1/${path}`, { headers });
      if (!res.ok) throw new Error(`upstream ${res.status} for ${path.split("?")[0]}`);
      return res.json() as Promise<unknown>;
    },
  };
}

/** Latest positions date on or before the committed snapshot; else null. */
export function committedBookDate(
  snapshotDate: string | null | undefined,
  positionDates: readonly string[],
): string | null {
  if (!snapshotDate) return null;
  let best: string | null = null;
  for (const d of positionDates) {
    if (d <= snapshotDate && (best === null || d > best)) best = d;
  }
  return best;
}

function diffDays(a: string, b: string): number {
  const ms = Date.parse(`${a}T00:00:00Z`) - Date.parse(`${b}T00:00:00Z`);
  return Math.round(ms / 86_400_000);
}

export interface NavTip {
  date: string;
  nav: number;
  contract: "finalized_accounting" | "legacy_estimate" | null;
  invested_pct: number | null;
  cash_pct: number | null;
}

export interface PositionRow {
  ticker: string;
  weight_pct: number;
  is_cash: boolean;
}

/** Contract section 6.1 response body builder (pure — vitest parity target). */
export function buildPortfolioBody(
  bookAsOf: string,
  navTip: NavTip | null,
  positions: PositionRow[],
): Record<string, unknown> {
  const heldSum = positions
    .filter((p) => !p.is_cash)
    .reduce((acc, p) => acc + (Number.isFinite(p.weight_pct) ? p.weight_pct : 0), 0);
  // Fallback order: NAV tip -> non-CASH weight sum -> null. Never invent.
  const kpiPct = navTip?.invested_pct ?? (positions.length > 0 ? heldSum : null);
  const envelopePct = kpiPct === null ? null : Math.min(100, kpiPct);
  const cashPct = envelopePct === null ? null : 100 - envelopePct;
  const tipDate = navTip?.date ?? null;
  // Scaffold seam: calendar-day lag between the NAV tip and the committed
  // book. Slice 0004 refines this with the metrics stamp.
  const lagDays = tipDate === null ? 0 : diffDays(tipDate, bookAsOf);
  return {
    book_as_of: bookAsOf,
    nav_tip: navTip
      ? {
          date: navTip.date,
          nav: navTip.nav,
          contract: navTip.contract,
          invested_pct: navTip.invested_pct,
          cash_pct: navTip.cash_pct,
          day_return_pct: null,
        }
      : null,
    seam: {
      crosses_nav_seam: lagDays !== 0,
      lag_days: lagDays,
      lag_direction: lagDays >= 0 ? "metrics lag" : "nav lag",
    },
    invested: { kpi_pct: kpiPct, envelope_pct: envelopePct, cash_pct: cashPct },
    positions,
  };
}

async function handlePortfolio(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  let params: CommonParams;
  try {
    params = parseCommonParams(url);
  } catch (e) {
    return e as Response;
  }
  const { asOf, retrievalPin } = params;

  if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_ROLE_KEY) {
    // Fail closed — never synthesize numbers without the book upstream.
    return errorResponse("upstream_empty", "book upstream not configured", retrievalPin);
  }
  const rest = restClient(env, retrievalPin);
  try {
    const snapshotPath =
      `daily_snapshots?select=date&order=date.desc&limit=1` +
      (asOf ? `&date=lte.${asOf}` : "");
    const snapshots = (await rest.getJson(snapshotPath)) as Array<{ date: string }>;
    const snapshotDate = snapshots[0]?.date ?? null;
    if (!snapshotDate) {
      return errorResponse("not_found", "no committed book for asOf", retrievalPin, { asOf });
    }

    const posDates = (await rest.getJson(
      `positions?select=date&workspace_id=eq.${HOUSE_WORKSPACE_ID}&order=date.desc&limit=500`,
    )) as Array<{ date: string }>;
    const bookAsOf = committedBookDate(
      snapshotDate,
      posDates.map((r) => r.date),
    );
    if (!bookAsOf) {
      // Never silently substitute the latest position date as "committed".
      return errorResponse("not_found", "no committed book for asOf", retrievalPin, {
        snapshot_date: snapshotDate,
      });
    }

    const [navRows, positionRows] = await Promise.all([
      rest.getJson(
        `public_accounting_nav_history?select=date,nav,invested_pct,cash_pct,contract&order=date.desc&limit=1`,
      ) as Promise<
        Array<{
          date: string;
          nav: number;
          invested_pct: number | null;
          cash_pct: number | null;
          contract: string | null;
        }>
      >,
      rest.getJson(
        `positions?select=ticker,weight_pct&workspace_id=eq.${HOUSE_WORKSPACE_ID}&date=eq.${bookAsOf}&limit=500`,
      ) as Promise<Array<{ ticker: string; weight_pct: number | null }>>,
    ]);
    const tip = navRows[0] ?? null;
    const navTip: NavTip | null = tip
      ? {
          date: tip.date,
          nav: tip.nav,
          contract:
            tip.contract === "finalized_accounting" || tip.contract === "legacy_estimate"
              ? tip.contract
              : null,
          invested_pct: tip.invested_pct,
          cash_pct: tip.cash_pct,
        }
      : null;
    const positions: PositionRow[] = positionRows.map((r) => ({
      ticker: r.ticker,
      weight_pct: Number(r.weight_pct ?? 0),
      is_cash: r.ticker.trim().toUpperCase() === "CASH",
    }));

    const provenance = buildProvenance({
      source: "public_accounting_nav_history+daily_snapshots+positions",
      tip_date: tipDate(tip),
      contract: navTip?.contract ?? null,
      seam: tipDate(tip) !== bookAsOf,
      marks: "unavailable",
    });
    return Response.json({
      data: buildPortfolioBody(bookAsOf, navTip, positions),
      as_of: bookAsOf,
      retrieval_pin: retrievalPin,
      provenance,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return errorResponse("upstream_empty", `book upstream read failed: ${message}`, retrievalPin);
  }
}

function tipDate(tip: { date: string } | null): string | null {
  return tip?.date ?? null;
}

async function handleHealthz(): Promise<Response> {
  return Response.json({ ok: true, service: "dashboard-api" });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = normalizePath(url.pathname);
    if (request.method === "GET" && path === "/healthz") return handleHealthz();
    if (request.method === "GET" && path === "/portfolio") return handlePortfolio(request, env);
    return errorResponse("bad_request", `unknown route ${path}`, null, { path });
  },
};
