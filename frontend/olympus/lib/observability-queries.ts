/**
 * Observability dashboard data access (Pillar 3D).
 *
 * Reads the decision track record (`decision_log`) the Decision Scorecard needs, plus
 * — via `fetchAtlasRunDiagnostics` — run health from the anon-readable
 * `atlas_run_health` view (migration 041). Kept separate from `getFullDashboardData`
 * so the main Morning Read bundle stays lean; these fire only when their consumer mounts.
 *
 * Attribution and recommendation quality now live on Portfolio Attribution; per-position
 * risk remains on Holdings. System reads run telemetry from `atlas_run_health` — the curated projection
 * that bypasses the base-table RLS on `atlas_run_diagnostics` (migration 033). Spend
 * telemetry (cost, tokens, error_summary, breakdown) is intentionally excluded from the
 * view; economics tiles render "—" on the public anon-key dashboard.
 *
 * Most queries are FAIL-SOFT: a missing/forbidden source (e.g. an empty book) resolves to an
 * empty result rather than throwing, so consumers render a clean empty state instead of an
 * error wall.
 *
 * Exception — accounting NAV (#2599 / #3029): `fetchOlympusTearsheet` FAILS CLOSED when
 * `public_accounting_nav_history` errors. Swallowing that into an empty series looked like
 * a healthy empty book and hid unapplied migrations 072–074.
 */

import { supabase, isSupabaseConfigured } from './supabase';
import type { TableRow, ViewRow } from './database.types';
import type { AtlasRunDiagnostics } from './types';
import type {
  BenchmarkComparison,
  OlympusTearsheet,
  PerformanceHoldingRow,
  PortfolioReturnPoint,
} from '@/components/tearsheet/types';
import type { ContributionReturnPoint } from '@digithings/web';
import { DASHBOARD_BENCHMARK_TICKERS } from './benchmark-tickers';
import {
  ACCOUNTING_NAV_VIEW,
  AccountingNavContractError,
  accountingNavToHistoryShape,
  type AccountingNavRow,
} from './accounting-views';

const DECISION_PAGE_SIZE = 1000;
const DECISION_MAX_ROWS = 50000;
const PERFORMANCE_HISTORY_LIMIT = 5000;
const ATTRIBUTION_LIMIT = 5000;

export interface ObservabilityData {
  decisions: TableRow<'decision_log'>[];
}

export interface PortfolioAttributionData {
  attribution: TableRow<'position_attribution'>[];
  attributionDate: string | null;
  decisions: TableRow<'decision_log'>[];
}

/** Run a single-table read, logging + swallowing any error into an empty array. */
async function safeSelect<T>(
  label: string,
  run: (sb: NonNullable<typeof supabase>) => PromiseLike<{ data: T[] | null; error: unknown }>
): Promise<{ rows: T[]; ok: boolean }> {
  if (!supabase) return { rows: [], ok: false };
  try {
    const { data, error } = await run(supabase);
    if (error) {
      console.error(`Supabase ${label} query:`, error);
      return { rows: [], ok: false };
    }
    return { rows: data ?? [], ok: true };
  } catch (err) {
    console.error(`Supabase ${label} query threw:`, err);
    return { rows: [], ok: false };
  }
}

async function fetchDecisionHistory(): Promise<TableRow<'decision_log'>[]> {
  const decisions: TableRow<'decision_log'>[] = [];
  for (let offset = 0; offset < DECISION_MAX_ROWS; offset += DECISION_PAGE_SIZE) {
    const page = await safeSelect<TableRow<'decision_log'>>('decision_log', (sb) =>
      sb
        .from('decision_log')
        .select(
          'id,run_id,run_date,ticker,stance,conviction,thesis,benchmark,holding_days,status,actual_return,alpha,reflection,resolved_at,created_at'
        )
        .order('run_date', { ascending: false })
        .range(offset, offset + DECISION_PAGE_SIZE - 1)
    );
    decisions.push(...page.rows);
    if (!page.ok || page.rows.length < DECISION_PAGE_SIZE) break;
  }
  return decisions;
}

export async function fetchObservabilityData(): Promise<ObservabilityData> {
  // Distinguish a total misconfiguration (no Supabase env) from a configured-but-empty book:
  // throw so the page shows a clear error, matching the main data layer (lib/queries.ts).
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY). ' +
        'Observability data cannot be loaded.'
    );
  }
  return { decisions: await fetchDecisionHistory() };
}

// Raised from 30 with migration 065 (#1762). The view now returns ONE ROW PER RETRY ATTEMPT,
// so a date that took three attempts consumes three slots instead of one. At 30 the timeline
// would show proportionally fewer distinct dates the moment retries became visible — and
// retries are not rare: 28 of the 54 rows extant at migration time were collapsed multi-attempt
// writes. 90 preserves ~30 distinct dates even if every one of them exhausts MAX_OUTER_ATTEMPTS.
const RUN_DIAGNOSTICS_LIMIT = 90;

/**
 * Read run health from the anon-readable `atlas_run_health` view (migration 041).
 * Cost/tokens/grounding fields are null on the public dashboard — the view
 * deliberately omits operator-internal spend telemetry. Fail-soft: empty array
 * on missing source / RLS deny.
 */
export async function fetchAtlasRunDiagnostics(): Promise<AtlasRunDiagnostics[]> {
  const res = await safeSelect<ViewRow<'atlas_run_health'>>('atlas_run_health', (sb) =>
    sb
      .from('atlas_run_health')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(RUN_DIAGNOSTICS_LIMIT)
  );
  return res.rows.map((r) => ({
    run_id: r.run_id,
    // `?? null` rather than `?? 1`: a row written before migration 065 carries 0, and a row
    // read from an un-migrated view carries undefined. Both mean "unknown", and defaulting
    // either to 1 would fabricate the provenance #1762 exists to stop fabricating.
    attempt: r.attempt ?? null,
    run_type: r.run_type,
    run_date: r.run_date,
    model: r.model,
    status: r.status,
    started_at: r.started_at,
    finished_at: r.finished_at,
    duration_s: r.duration_s,
    llm_calls: null,
    prompt_tokens: null,
    completion_tokens: null,
    total_tokens: null,
    cached_tokens: null,
    search_calls: null,
    grounding_ok: null,
    grounding_failed: null,
    est_cost_usd: null,
    segments_total: r.segments_total,
    segments_ok: r.segments_ok,
    segments_carried: r.segments_carried,
    segments_failed: r.segments_failed,
    error_summary: null,
    breakdown: null,
    created_at: r.created_at,
  }));
}

/* ── Performance tear sheet (Pillar 3C) ───────────────────────────────────────
  Reads persisted portfolio returns and stored attribution windows. Missing
  cumulative-return fields fall back to the same deterministic first/last
  history calculation used by the backend writer. */

/** Keep only the rows whose date equals the most recent date present. */
function latestDateRows<T extends { date: string | null }>(rows: T[]): { rows: T[]; date: string | null } {
  const date = rows.reduce<string | null>(
    (m, r) => (r.date && (m === null || r.date > m) ? r.date : m),
    null
  );
  return { rows: date === null ? [] : rows.filter((r) => r.date === date), date };
}

export function buildPortfolioAttributionData(args: {
  attribution: TableRow<'position_attribution'>[];
  decisions: TableRow<'decision_log'>[];
}): PortfolioAttributionData {
  const latestAttribution = latestDateRows(args.attribution);
  return {
    attribution: latestAttribution.rows,
    attributionDate: latestAttribution.date,
    decisions: args.decisions,
  };
}

export async function fetchPortfolioAttribution(): Promise<PortfolioAttributionData> {
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY). ' +
        'Portfolio attribution cannot be loaded.'
    );
  }

  const [attributionRes, observability] = await Promise.all([
    safeSelect<TableRow<'position_attribution'>>('position_attribution', (sb) =>
      sb
        .from('position_attribution')
        .select('*')
        .order('date', { ascending: false })
        .limit(ATTRIBUTION_LIMIT)
    ),
    fetchObservabilityData(),
  ]);
  return buildPortfolioAttributionData({
    attribution: attributionRes.rows,
    decisions: observability.decisions,
  });
}

function latestAttributionByTicker(
  rows: TableRow<'position_attribution'>[]
): Map<string, TableRow<'position_attribution'>> {
  const latest = new Map<string, TableRow<'position_attribution'>>();
  for (const row of [...rows].sort((a, b) => b.date.localeCompare(a.date))) {
    const ticker = row.ticker.toUpperCase();
    if (ticker !== 'CASH' && !latest.has(ticker)) latest.set(ticker, row);
  }
  return latest;
}

function toHoldingRow(
  ticker: string,
  position: TableRow<'positions'> | null,
  attribution: TableRow<'position_attribution'> | null,
  exit: TableRow<'position_events'> | null = null,
  isClosed = false
): PerformanceHoldingRow {
  const entryPrice = position?.entry_price;
  const exitPrice = exit?.price ?? position?.current_price;
  const realizedReturnPct =
    isClosed && entryPrice != null && entryPrice > 0 && exitPrice != null && exitPrice > 0
      ? roundPct((exitPrice / entryPrice - 1) * 100)
      : null;
  return {
    ticker,
    category:
      attribution?.sector_bucket ?? position?.sector_bucket ?? position?.category ?? null,
    weightPct: attribution?.weight_pct ?? position?.weight_pct ?? null,
    unrealizedReturnPct:
      position?.unrealized_pnl_pct ?? position?.since_entry_return_pct ?? null,
    realizedReturnPct,
    attributionDate:
      exit?.date ??
      attribution?.date ??
      position?.metrics_as_of ??
      (isClosed ? position?.date : null) ??
      null,
  };
}

function roundPct(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}

function periodReturnPct(values: number[]): number | null {
  if (values.length < 2) return null;
  const first = values[0];
  const last = values.at(-1);
  if (last == null || first <= 0 || !Number.isFinite(first) || !Number.isFinite(last)) {
    return null;
  }
  return roundPct((last / first - 1) * 100);
}

function buildPortfolioReturnSeries(
  nav: TableRow<'nav_history'>[]
): PortfolioReturnPoint[] {
  const sorted = [...nav].sort((a, b) => a.date.localeCompare(b.date));
  const baseline = sorted.find((row) => Number.isFinite(row.nav) && row.nav > 0)?.nav;
  if (baseline == null) return [];
  return sorted
    .filter((row) => Number.isFinite(row.nav) && row.nav > 0)
    .map((row) => ({
      date: row.date,
      nav: row.nav,
      returnPct: roundPct((row.nav / baseline - 1) * 100),
    }));
}

function buildBenchmarkComparisons(
  navSeries: PortfolioReturnPoint[],
  prices: Array<{ ticker?: string; date: string; close: number }>,
  fallbackTicker: string
): BenchmarkComparison[] {
  if (navSeries.length < 2) return [];
  const grouped = new Map<string, Array<{ date: string; close: number }>>();
  for (const row of prices) {
    if (!Number.isFinite(row.close) || row.close <= 0) continue;
    const ticker = (row.ticker ?? fallbackTicker).toUpperCase();
    if (!grouped.has(ticker)) grouped.set(ticker, []);
    grouped.get(ticker)!.push(row);
  }

  const order = new Map<string, number>(
    DASHBOARD_BENCHMARK_TICKERS.map((ticker, index) => [ticker, index])
  );
  return [...grouped.entries()]
    .map(([ticker, rows]): BenchmarkComparison | null => {
      const sorted = [...rows].sort((left, right) => left.date.localeCompare(right.date));
      if (sorted.length < 2) return null;
      const baseline = sorted[0].close;
      let priceIndex = -1;
      const series = navSeries.map((point) => {
        while (priceIndex + 1 < sorted.length && sorted[priceIndex + 1].date <= point.date) {
          priceIndex += 1;
        }
        const close = priceIndex >= 0 ? sorted[priceIndex].close : baseline;
        return { date: point.date, returnPct: roundPct((close / baseline - 1) * 100) };
      });
      return { ticker, returnPct: series.at(-1)!.returnPct, series };
    })
    .filter((comparison): comparison is BenchmarkComparison => comparison != null)
    .sort(
      (left, right) =>
        (order.get(left.ticker) ?? Number.MAX_SAFE_INTEGER) -
          (order.get(right.ticker) ?? Number.MAX_SAFE_INTEGER) ||
        left.ticker.localeCompare(right.ticker)
    );
}

function buildPositionContributionSeries(
  navSeries: PortfolioReturnPoint[],
  positions: TableRow<'positions'>[],
  currentTickers: Set<string>
): ContributionReturnPoint[] {
  if (!navSeries.length) return [];

  const snapshots = new Map<string, Map<string, TableRow<'positions'>>>();
  const pricesByTicker = new Map<string, Array<{ date: string; price: number }>>();
  for (const row of positions) {
    const ticker = row.ticker.toUpperCase();
    if (ticker === 'CASH' || !currentTickers.has(ticker)) continue;
    if (!snapshots.has(row.date)) snapshots.set(row.date, new Map());
    snapshots.get(row.date)!.set(ticker, row);
    if (row.current_price != null && row.current_price > 0) {
      if (!pricesByTicker.has(ticker)) pricesByTicker.set(ticker, []);
      pricesByTicker.get(ticker)!.push({ date: row.date, price: row.current_price });
    }
  }

  const snapshotDates = [...snapshots.keys()].sort();
  const cumulativeByTicker = new Map<string, number[]>();
  for (const [ticker, rawPrices] of pricesByTicker) {
    const prices = [...rawPrices].sort((left, right) => left.date.localeCompare(right.date));
    const cumulative: number[] = [0];
    let snapshotIndex = -1;
    let priceIndex = -1;
    let priorWeight = 0;
    let priorPrice: number | null = null;
    let hasComparableInterval = false;

    for (let index = 0; index < navSeries.length; index += 1) {
      const date = navSeries[index].date;
      while (snapshotIndex + 1 < snapshotDates.length && snapshotDates[snapshotIndex + 1] <= date) {
        snapshotIndex += 1;
      }
      while (priceIndex + 1 < prices.length && prices[priceIndex + 1].date <= date) {
        priceIndex += 1;
      }

      const snapshot = snapshotIndex >= 0 ? snapshots.get(snapshotDates[snapshotIndex]) : null;
      const weight = snapshot?.get(ticker)?.weight_pct ?? 0;
      const price = priceIndex >= 0 ? prices[priceIndex].price : null;
      if (index > 0) {
        let next = cumulative[index - 1];
        if (priorPrice != null && price != null && priorPrice > 0) {
          next += priorWeight * (price / priorPrice - 1);
          hasComparableInterval = true;
        }
        cumulative.push(roundPct(next));
      }
      priorWeight = weight;
      priorPrice = price;
    }

    if (hasComparableInterval) cumulativeByTicker.set(ticker, cumulative);
  }

  return navSeries.map((point, index) => ({
    t: point.date,
    returnPct: point.returnPct,
    contributions: Object.fromEntries(
      [...cumulativeByTicker.entries()]
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([ticker, values]) => [ticker, values[index]])
    ),
  }));
}

function latestExitByTicker(
  events: TableRow<'position_events'>[]
): Map<string, TableRow<'position_events'>> {
  const latest = new Map<string, TableRow<'position_events'>>();
  for (const event of [...events].sort((a, b) => b.date.localeCompare(a.date))) {
    const ticker = event.ticker.toUpperCase();
    if (event.event === 'EXIT' && !latest.has(ticker)) latest.set(ticker, event);
  }
  return latest;
}

function latestPositionByTicker(
  positions: TableRow<'positions'>[]
): Map<string, TableRow<'positions'>> {
  const latest = new Map<string, TableRow<'positions'>>();
  for (const position of [...positions].sort((a, b) => b.date.localeCompare(a.date))) {
    const ticker = position.ticker.toUpperCase();
    if (ticker !== 'CASH' && !latest.has(ticker)) latest.set(ticker, position);
  }
  return latest;
}

export function buildOlympusTearsheet(args: {
  nav: TableRow<'nav_history'>[];
  positions: TableRow<'positions'>[];
  metrics: TableRow<'portfolio_metrics'> | null;
  attribution: TableRow<'position_attribution'>[];
  events?: TableRow<'position_events'>[];
  benchmarkPrices?: Array<{ ticker?: string; date: string; close: number }>;
}): OlympusTearsheet {
  const navAsc = [...args.nav].sort((a, b) => a.date.localeCompare(b.date));
  const inceptionDate = navAsc[0]?.date ?? null;
  const navSeries = buildPortfolioReturnSeries(navAsc);
  const currentSnapshot = latestDateRows(args.positions);
  const currentPositions = currentSnapshot.rows.filter(
    (position) => position.ticker.toUpperCase() !== 'CASH' && position.weight_pct > 0
  );
  const attributionByTicker = latestAttributionByTicker(args.attribution);
  const exitByTicker = latestExitByTicker(args.events ?? []);
  const latestPosition = latestPositionByTicker(args.positions);
  const latestAttribution = latestDateRows(args.attribution);
  const currentTickers = new Set(
    (currentPositions.length ? currentPositions : latestAttribution.rows)
      .filter((row) => row.ticker.toUpperCase() !== 'CASH')
      .map((row) => row.ticker.toUpperCase())
  );
  const positionByTicker = new Map(
    currentPositions.map((position) => [position.ticker.toUpperCase(), position])
  );
  const currentHoldings = [...currentTickers]
    .map((ticker) =>
      toHoldingRow(
        ticker,
        positionByTicker.get(ticker) ?? null,
        attributionByTicker.get(ticker) ?? null
      )
    )
    .sort((a, b) => (b.weightPct ?? 0) - (a.weightPct ?? 0));
  const historicalTickers = new Set([
    ...[...attributionByTicker.keys()].filter((ticker) => !currentTickers.has(ticker)),
    ...[...exitByTicker.keys()].filter((ticker) => !currentTickers.has(ticker)),
  ]);
  const historicalHoldings = [...historicalTickers]
    .map((ticker) =>
      toHoldingRow(
        ticker,
        latestPosition.get(ticker) ?? null,
        attributionByTicker.get(ticker) ?? null,
        exitByTicker.get(ticker) ?? null,
        true
      )
    )
    .sort(
      (a, b) =>
        (b.attributionDate ?? '').localeCompare(a.attributionDate ?? '') ||
        Math.abs(b.realizedReturnPct ?? 0) - Math.abs(a.realizedReturnPct ?? 0)
    );
  // Accounting NAV series is the single source of truth for since-inception %.
  // Prefer derived over persisted metrics so a stale/wrong net_return_pct cannot
  // show a positive portfolio return while the base-100 index sits under 100.
  const derivedNetReturnPct = periodReturnPct(navAsc.map((row) => row.nav));
  const persistedBenchmarkTicker = args.metrics?.benchmark_ticker ?? 'SPY';
  const benchmarkComparisons = buildBenchmarkComparisons(
    navSeries,
    args.benchmarkPrices ?? [],
    persistedBenchmarkTicker
  );
  const defaultComparison =
    benchmarkComparisons.find((comparison) => comparison.ticker === 'SPY') ??
    benchmarkComparisons.find((comparison) => comparison.ticker === persistedBenchmarkTicker) ??
    benchmarkComparisons[0];
  const derivedBenchmarkReturnPct = defaultComparison?.returnPct ?? null;
  const netReturnPct = derivedNetReturnPct ?? args.metrics?.net_return_pct ?? null;
  const benchmarkReturnPct =
    derivedBenchmarkReturnPct ?? args.metrics?.benchmark_return_pct ?? null;
  const relativeReturnPct =
    netReturnPct != null && benchmarkReturnPct != null
      ? roundPct(netReturnPct - benchmarkReturnPct)
      : args.metrics?.relative_return_pct ?? null;
  const persistedUsed = [
    args.metrics?.net_return_pct,
    args.metrics?.benchmark_return_pct,
    args.metrics?.relative_return_pct,
  ].some((value) => value != null);
  // Derived wins for portfolio return whenever the NAV series can produce one.
  const derivedUsed = derivedNetReturnPct != null || derivedBenchmarkReturnPct != null;
  const returnsSource = persistedUsed
    ? derivedUsed
      ? 'mixed'
      : 'persisted'
    : derivedUsed
      ? 'derived'
      : 'unavailable';

  return {
    currentNav: navAsc.at(-1)?.nav ?? null,
    netReturnPct,
    benchmarkReturnPct,
    relativeReturnPct,
    benchmarkTicker: defaultComparison?.ticker ?? persistedBenchmarkTicker,
    benchmarkComparisons,
    returnsSource,
    metricsAsOf:
      derivedUsed
        ? navAsc.at(-1)?.date ?? args.metrics?.as_of_date ?? args.metrics?.date ?? null
        : args.metrics?.as_of_date ?? args.metrics?.date ?? null,
    inceptionDate,
    holdingsAsOf: currentSnapshot.date ?? latestAttribution.date,
    generatedAt: args.metrics?.generated_at ?? null,
    navSeries,
    contributionSeries: buildPositionContributionSeries(
      navSeries,
      args.positions,
      currentTickers
    ),
    currentHoldings,
    historicalHoldings,
  };
}

export async function fetchOlympusTearsheet(): Promise<OlympusTearsheet> {
  if (!isSupabaseConfigured() || !supabase) {
    // Configured-but-empty must still render the empty-state tear sheet — return a zeroed build.
    return buildOlympusTearsheet({
      nav: [],
      positions: [],
      metrics: null,
      attribution: [],
      events: [],
    });
  }
  // NAV: curated accounting series (#2599). Fail closed on query error (#3029) —
  // never build an empty tearsheet that looks like a healthy empty book.
  // Query directly (not via safeSelect) so the PostgREST error is preserved.
  const navQuery = await supabase
    .from(ACCOUNTING_NAV_VIEW)
    .select('date,nav,cash_pct,invested_pct,day_return_pct,source,contract')
    .order('date', { ascending: true })
    .limit(PERFORMANCE_HISTORY_LIMIT);
  if (navQuery.error) {
    throw new AccountingNavContractError(navQuery.error);
  }
  const navRows = (navQuery.data ?? []) as AccountingNavRow[];

  const [positionsRes, metricsRes, attributionRes, eventsRes] = await Promise.all([
    safeSelect<TableRow<'positions'>>('positions', (sb) =>
      sb
        .from('positions')
        .select('*')
        .order('date', { ascending: false })
        .limit(PERFORMANCE_HISTORY_LIMIT)
    ),
    safeSelect<TableRow<'portfolio_metrics'>>('portfolio_metrics', (sb) =>
      sb.from('portfolio_metrics').select('*').order('date', { ascending: false }).limit(1)
    ),
    // Book attribution tab stays on current-book lookback (diagnostic). Realized daily
    // contribution is public_daily_realized_attribution — do not mix into this series.
    safeSelect<TableRow<'position_attribution'>>('position_attribution', (sb) =>
      sb
        .from('position_attribution')
        .select('*')
        .order('date', { ascending: false })
        .limit(ATTRIBUTION_LIMIT)
    ),
    safeSelect<TableRow<'position_events'>>('position_events', (sb) =>
      sb
        .from('position_events')
        .select('*')
        .eq('event', 'EXIT')
        .order('date', { ascending: false })
        .limit(PERFORMANCE_HISTORY_LIMIT)
    ),
  ]);
  const navHistory: TableRow<'nav_history'>[] = navRows.map((row) => {
    const shaped = accountingNavToHistoryShape(row);
    return {
      date: shaped.date,
      nav: shaped.nav,
      cash_pct: shaped.cash_pct,
      invested_pct: shaped.invested_pct,
    };
  });
  const navWindow = [...navHistory]
    .filter((row) => Number.isFinite(row.nav) && row.nav > 0)
    .sort((left, right) => left.date.localeCompare(right.date));
  const benchmarkRes =
    navWindow.length >= 2
      ? await safeSelect<Pick<TableRow<'price_history'>, 'ticker' | 'date' | 'close'>>(
          'benchmark price_history',
          (sb) =>
            sb
              .from('price_history')
              .select('ticker,date,close')
              .in('ticker', [...DASHBOARD_BENCHMARK_TICKERS])
              .gte('date', navWindow[0].date)
              .lte('date', navWindow.at(-1)!.date)
              .order('date', { ascending: true })
              .limit(PERFORMANCE_HISTORY_LIMIT)
        )
      : { rows: [], ok: true };
  return buildOlympusTearsheet({
    nav: navHistory,
    positions: positionsRes.rows,
    metrics: metricsRes.rows[0] ?? null,
    attribution: attributionRes.rows,
    events: eventsRes.rows,
    benchmarkPrices: benchmarkRes.rows,
  });
}
