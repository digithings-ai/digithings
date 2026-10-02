/**
 * DigiQuant API client — the dashboard-api worker (apps/dashboard-api,
 * CONTRACT.md §6). Every data block binds to one route here.
 */
export type Envelope<T> = {
  data: T;
  as_of: string | null;
  retrieval_pin: string | null;
  provenance: { source: string; marks: 'stored' | 'market_api' | 'unavailable'; tip_date?: string | null };
};

export type BookRow = {
  ticker: string;
  scaled_weight_pct: number;
  entry_price: number | null;
  current_price: number | null;
  unrealized_pct: number | null;
  /** Proposed /allocations extension (BLOCKS.md). Absent until the worker ships them → "—". */
  name?: string | null;
  sleeve?: string | null;
  shares?: number | null;
  value?: number | null;
  day_return_pct?: number | null;
  thesis_id?: string | null;
  is_cash?: boolean;
};

export type Book = {
  book_as_of: string | null;
  rows: BookRow[];
  /** Proposed extension. */
  cash_value?: number | null;
  book_value?: number | null;
  sleeves?: { sleeve: string; names: number; weight_pct: number }[];
};

/** Proposed routes (BLOCKS.md): not in CONTRACT yet. */
export type Theses = {
  theses: { id: string; name: string; state: 'active' | 'watch' | 'exited'; vehicles: string[]; evidence: string | null; kill_condition: string | null; note?: string | null }[];
  counts: { active: number; watch: number; exited: number };
};
export type Attribution = {
  window: { start: string; end: string };
  sleeves: { sleeve: string; contribution_bp: number | null }[];
  names: { ticker: string; sleeve: string | null; contribution_bp: number | null }[];
};
export type CashLedger = { entries: { date: string; kind: string; amount: number | null; balance: number | null }[] };

/** Route payloads (CONTRACT §6). Nullable numbers stay nullable: null renders "—". */
export type Portfolio = {
  book_as_of: string | null;
  nav_tip: { date: string; nav: number; contract: string; invested_pct: number | null; cash_pct: number | null; day_return_pct: number | null } | null;
  seam: { crosses_nav_seam: boolean; lag_days: number; lag_direction: string } | null;
  invested: { kpi_pct: number | null; envelope_pct: number | null; cash_pct: number | null; definition: string };
  positions: { ticker: string; weight_pct: number; scaled_weight_pct: number; is_cash: boolean }[];
};
export type Brief = {
  book_as_of: string | null;
  nav_tip: { date: string; nav: number; contract: string } | null;
  day_return_pct: number | null;
  since_inception_pct: number | null;
  since_inception_start_date: string | null;
  overlay: { active: boolean; live_vs_mark_pct: number; badge: string };
  invested_pct: number | null;
  session_events: unknown[];
  /** Proposed extensions. */
  decision?: { lead: string; body: string | null; run_date: string | null } | null;
  risks?: string[];
};
export type Performance = {
  nav: { tip_date: string; base100_tip: number; points: { date: string; index: number; day_return_pct: number | null }[] };
  metrics: { day_return_pct: number | null; since_inception_pct: number | null; excess_return_pct: number | null; alpha_pct: number | null; information_ratio: number | null; beta: number | null; overlap_days: number };
  benchmark: { ticker: string; aligned_start: string };
  /** Proposed extension. */
  drawdown?: { max_pct: number | null; peak_date: string | null; trough_date: string | null; current_pct: number | null };
};
export type KpisLive = {
  quote_date: string; live_vs_mark_pct: number; day_return_live_pct: number | null;
  since_inception_live_pct: number | null; excess_live_pct: number | null; overlay_eligible: boolean; universe: string[];
};
export type NavSeries = { tip: { date: string; contract: string }; points: { index: number; date: string; nav: number; day_return_pct: number | null; contract: string }[] };
export type Benchmarks = { universe: string[]; series: Record<string, { date: string; close: number }[]>; aligned_start: string; overlap_days: number };
export type Ledger = {
  events: { date: string; ticker: string; type: 'OPEN' | 'ADD' | 'EXIT' | 'TRIM'; fill_price: number | null; avg_entry: number | null; realized_pct: number | null; prev_weight_pct: number | null; weight_pct: number | null }[];
  next_cursor: string | null;
};

/** Local `wrangler dev` (dashboard-api). Override with NEXT_PUBLIC_DQ_API_URL. */
const DEFAULT_API = 'http://127.0.0.1:8788';
const base = () => {
  const raw = (process.env.NEXT_PUBLIC_DQ_API_URL ?? '').trim();
  return (raw || DEFAULT_API).replace(/\/+$/, '');
};

async function failText(res: Response, route: string): Promise<string> {
  let detail = '';
  try {
    const body = (await res.json()) as { error?: { message?: string } };
    if (body?.error?.message) detail = `: ${body.error.message}`;
  } catch { /* status is enough when the body is not JSON */ }
  return `${route} failed (${res.status})${detail}`;
}

export async function dqGet<T>(route: string): Promise<Envelope<T>> {
  const res = await fetch(`${base()}${route}`);
  if (!res.ok) throw new Error(await failText(res, route));
  const body: unknown = await res.json();
  if (!body || typeof body !== 'object' || (body as { data?: unknown }).data == null) throw new Error(`${route} returned no data`);
  const env = body as Envelope<T>;
  return { ...env, retrieval_pin: env.retrieval_pin ?? null };
}

/** Write route (PUT/POST/DELETE). Throws with the route and status; never pretends a write succeeded. */
export async function dqSend<T = unknown>(method: 'PUT' | 'POST' | 'DELETE', route: string, body?: unknown): Promise<T | null> {
  const res = await fetch(`${base()}${route}`, {
    method,
    headers: body === undefined ? undefined : { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await failText(res, `${method} ${route}`));
  return res.status === 204 ? null : ((await res.json()) as T);
}

/** Fail closed to an em dash — never invent a number. */
export const pct = (v: number | null) => (v === null || !Number.isFinite(v) ? '—' : `${v.toFixed(2)}%`);
export const px = (v: number | null) => (v === null || !Number.isFinite(v) ? '—' : v.toFixed(2));
export const signed = (v: number | null) => (v === null || !Number.isFinite(v) ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`);
