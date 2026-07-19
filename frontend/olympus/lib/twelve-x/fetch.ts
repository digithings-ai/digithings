/**
 * Typed fetchers for the twelve-x FX research tables.
 *
 * Mirrors the `querySupabase` retry/guard pattern in `lib/queries.ts`, but runs
 * against the dedicated twelve-x client (`./supabase`) rather than the main
 * Olympus singleton. All selects are cast to the contract row types in
 * `./types.ts`.
 *
 * Empty-state philosophy (per the suite spec): the FX digest relaxes the
 * Atlas "today / yesterday only" window — there is no daily-freshness banner,
 * so `getLatestDigest()` simply returns the latest covered session.
 */
import type { SupabaseClient } from '@supabase/supabase-js';
import { isTwelveXConfigured, twelveXSupabase } from './supabase';
import { isSupabaseConfigured, supabase } from '../supabase';
import { MATRIX_COLUMNS } from './types';
import type {
  ConfluenceCatalyst,
  ConsensusDelta,
  ConsensusDeltaSet,
  CurrencyView,
  FxBriefRow,
  FxConfluenceSnapshotRow,
  FxConsensusSnapshotRow,
  FxDailyDigestRow,
  FxEconomicCalendarRow,
  FxEventSnapshotRow,
  FxLedgerRow,
  FxTradeIdeaRow,
  IntelligenceWhy,
  IntelligenceWhyComponents,
  IntelligenceWhyConsensus,
  IntelligenceWhyDesk,
  IntelligenceWhyItem,
  MatrixCell,
  MatrixCellHistoryEntry,
  MatrixColumn,
  Mover,
  Timeframe,
} from './types';

/**
 * Run a twelve-x Supabase query with bounded exponential-backoff retries.
 *
 * Empty-data semantics: PostgREST returns `data = []` for an empty table and
 * `data = null` ONLY on error (where `error` is also set). A `null`/`undefined`
 * payload with NO error is therefore treated as an EMPTY result (the fallback,
 * default `[]`) rather than a failure — so a brand-new/empty snapshot table
 * renders an empty state instead of crashing the tab. Genuine errors still
 * throw and exhaust the retry budget.
 */
async function querySupabase<T>(
  queryFn: (sb: SupabaseClient) => PromiseLike<{ data: T | null; error: unknown }>,
  {
    retries = 3,
    delayMs = 500,
    emptyValue = [] as unknown as T,
  }: { retries?: number; delayMs?: number; emptyValue?: T } = {}
): Promise<T> {
  if (!isTwelveXConfigured() || !twelveXSupabase) {
    throw new Error(
      'twelve-x Supabase is not configured. Set NEXT_PUBLIC_TWELVEX_SUPABASE_URL / ' +
        'NEXT_PUBLIC_TWELVEX_SUPABASE_ANON_KEY (or the shared NEXT_PUBLIC_SUPABASE_* vars).'
    );
  }
  let lastError: unknown;
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const { data, error } = await queryFn(twelveXSupabase);
      if (error) throw error;
      // No error + no data == empty result, not a failure.
      if (data == null) return emptyValue;
      return data;
    } catch (err) {
      lastError = err;
      if (attempt < retries - 1) {
        await new Promise((r) => setTimeout(r, delayMs * Math.pow(2, attempt)));
      }
    }
  }
  throw lastError;
}

/**
 * Empty-tolerant query against the MAIN Olympus client (the `core` project), for the
 * shared `economic_calendar` (#1066). The calendar moved out of the twelve-x project
 * into `core`'s shared data layer, so it is read via the main client — unlike the other
 * FX research tables, which stay on `twelveXSupabase`. Same empty == `[]` semantics as
 * {@link querySupabase} so an empty calendar renders an empty state, not a crash.
 */
async function queryMainSupabase<T>(
  queryFn: (sb: SupabaseClient) => PromiseLike<{ data: T | null; error: unknown }>,
  {
    retries = 3,
    delayMs = 500,
    emptyValue = [] as unknown as T,
  }: { retries?: number; delayMs?: number; emptyValue?: T } = {}
): Promise<T> {
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Olympus Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY.'
    );
  }
  let lastError: unknown;
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      const { data, error } = await queryFn(supabase as unknown as SupabaseClient);
      if (error) throw error;
      if (data == null) return emptyValue;
      return data;
    } catch (err) {
      lastError = err;
      if (attempt < retries - 1) {
        await new Promise((r) => setTimeout(r, delayMs * Math.pow(2, attempt)));
      }
    }
  }
  throw lastError;
}

/** Normalize `key_themes` (jsonb array OR text[] OR null) to a clean string[]. */
export function normalizeKeyThemes(raw: FxDailyDigestRow['key_themes']): string[] {
  if (Array.isArray(raw)) {
    return raw.map((x) => String(x)).filter((s) => s.trim().length > 0);
  }
  if (typeof raw === 'string') {
    const trimmed = raw.trim();
    if (!trimmed) return [];
    // Tolerate a JSON-encoded array string.
    if (trimmed.startsWith('[')) {
      try {
        const parsed = JSON.parse(trimmed);
        if (Array.isArray(parsed)) {
          return parsed.map((x) => String(x)).filter((s) => s.trim().length > 0);
        }
      } catch {
        /* fall through */
      }
    }
    return [trimmed];
  }
  return [];
}

/**
 * All weighted (live, relevance-weighted) consensus rows across every run_date,
 * ordered oldest→newest by date then currency — ready for per-currency time
 * series. Returns `[]` when twelve-x is unconfigured.
 */
export async function getConsensusTimeSeries(
  timeframe: Timeframe = 'medium'
): Promise<FxConsensusSnapshotRow[]> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return [];
  const rows = await querySupabase<FxConsensusSnapshotRow[]>((sb) =>
    sb
      .from('fx_consensus_snapshot')
      .select(
        'run_date, currency, weighted, score, confidence, agreement, tilt, n_eff, n_brokers, n_views, bullish_pct, bearish_pct, neutral_pct, watch_pct, as_of, timeframe, horizon_weeks'
      )
      .eq('weighted', true)
      .eq('timeframe', timeframe)
      .order('run_date', { ascending: true })
      .order('currency', { ascending: true })
  );
  return rows ?? [];
}

/**
 * PURE — no fetch. Compute the run-over-run consensus delta picture from a
 * timeframe-pinned series (sorted oldest→newest, one row per currency per run).
 * Takes the two newest distinct run_dates; per currency in the newest run it
 * derives the score/confidence deltas and a direction-flip flag, then ranks the
 * biggest absolute score shifts as the top-6 movers.
 */
export function computeConsensusDeltaSet(series: FxConsensusSnapshotRow[]): ConsensusDeltaSet {
  if (series.length === 0) {
    return { runDate: null, prevRunDate: null, byCurrency: {}, movers: [] };
  }

  // Distinct run_dates present, newest-first (series is oldest→newest).
  const dates: string[] = [];
  for (let i = series.length - 1; i >= 0; i--) {
    const d = series[i].run_date;
    if (!dates.includes(d)) {
      dates.push(d);
      if (dates.length >= 2) break;
    }
  }
  const runDate = dates[0] ?? null;
  const prevRunDate = dates[1] ?? null;

  const nowRows = series.filter((r) => r.run_date === runDate);
  const prevByCcy = new Map<string, FxConsensusSnapshotRow>();
  if (prevRunDate) {
    for (const r of series) {
      if (r.run_date === prevRunDate) prevByCcy.set(r.currency, r);
    }
  }

  const byCurrency: Record<string, ConsensusDelta> = {};
  const movers: Mover[] = [];
  for (const row of nowRows) {
    const prev = prevByCcy.get(row.currency) ?? null;
    const scoreNow = row.score;
    const scorePrev = prev ? prev.score : null;
    const scoreDelta = prev ? scoreNow - prev.score : null;
    const confidenceDelta = prev ? row.confidence - prev.confidence : null;
    const flippedDirection =
      !!prev &&
      Math.sign(scoreNow) !== Math.sign(prev.score) &&
      Math.abs(scoreNow - prev.score) > 0.05;
    const delta: ConsensusDelta = {
      currency: row.currency,
      scoreNow,
      scorePrev,
      scoreDelta,
      confidenceDelta,
      flippedDirection,
      prevRunDate,
    };
    byCurrency[row.currency] = delta;
    if (scoreDelta != null) {
      movers.push({
        currency: row.currency,
        scoreNow,
        scoreDelta,
        absDelta: Math.abs(scoreDelta),
        direction: scoreDelta >= 0 ? 'up' : 'down',
      });
    }
  }

  movers.sort((a, b) => b.absDelta - a.absDelta);

  return { runDate, prevRunDate, byCurrency, movers: movers.slice(0, 6) };
}

/**
 * The latest FX daily digest. Relaxed empty-state window: returns whatever the
 * freshest covered session is (no today/yesterday gate). `null` when
 * unconfigured or the table is empty.
 */
export async function getLatestDigest(): Promise<
  (Omit<FxDailyDigestRow, 'key_themes'> & { key_themes: string[] }) | null
> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return null;
  const rows = await querySupabase<FxDailyDigestRow[]>((sb) =>
    sb
      .from('fx_daily_digest')
      .select('run_date, summary, key_themes, doc_count, broker_count')
      .order('run_date', { ascending: false })
      .limit(1)
  );

  const row = rows?.[0];
  if (!row) return null;
  return {
    run_date: row.run_date,
    summary: row.summary,
    key_themes: normalizeKeyThemes(row.key_themes),
    doc_count: Number(row.doc_count ?? 0),
    broker_count: Number(row.broker_count ?? 0),
  };
}

/**
 * Top-N confluence trade ideas for a given run_date, ascending by rank
 * (rank 1 = strongest). Returns `[]` when unconfigured or none exist.
 */
export async function getTopConfluence(
  runDate: string,
  limit = 6
): Promise<FxConfluenceSnapshotRow[]> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return [];
  if (!runDate) return [];
  const rows = await querySupabase<FxConfluenceSnapshotRow[]>((sb) =>
    sb
      .from('fx_confluence_snapshot')
      .select('run_date, rank, title, currency, direction, score, components, brief_keys, as_of')
      .eq('run_date', runDate)
      .order('rank', { ascending: true })
      .limit(limit)
  );
  return rows ?? [];
}

/** Resolve the latest run_date present in `fx_confluence_snapshot`, or `null`. */
async function getLatestConfluenceDate(): Promise<string | null> {
  const latest = await querySupabase<{ run_date: string }[]>((sb) =>
    sb
      .from('fx_confluence_snapshot')
      .select('run_date')
      .order('run_date', { ascending: false })
      .limit(1)
  );
  return latest?.[0]?.run_date ?? null;
}

/**
 * Ranked confluence trade ideas for the Intelligence tab. Defaults to the latest
 * run_date in `fx_confluence_snapshot`; pass `runDate` to pin a specific session.
 * Returns the full ranked set (rank 1 = strongest). `[]` when unconfigured/empty.
 */
export async function getIntelligence(
  runDate?: string,
  limit = 24
): Promise<FxConfluenceSnapshotRow[]> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return [];
  const date = runDate ?? (await getLatestConfluenceDate());
  if (!date) return [];
  const rows = await querySupabase<FxConfluenceSnapshotRow[]>((sb) =>
    sb
      .from('fx_confluence_snapshot')
      .select('run_date, rank, title, currency, direction, score, components, brief_keys, as_of')
      .eq('run_date', date)
      .order('rank', { ascending: true })
      .limit(limit)
  );
  return rows ?? [];
}

/**
 * Upcoming macro catalysts from the shared `economic_calendar` (core): today → +14 days,
 * ordered by the absolute UTC release instant (NULL release times — all-day rows —
 * sort last, then by event_date). Returns `[]` when unconfigured or none exist.
 */
export async function getUpcomingEvents(): Promise<FxEconomicCalendarRow[]> {
  // #1066: the calendar lives in the shared `core` project now, so it is read via the
  // MAIN Olympus client (not `twelveXSupabase`), from `economic_calendar`.
  if (!isSupabaseConfigured() || !supabase) return [];
  const today = new Date();
  const start = today.toISOString().slice(0, 10);
  const horizon = new Date(today.getTime() + 14 * 24 * 60 * 60 * 1000);
  const end = horizon.toISOString().slice(0, 10);
  const rows = await queryMainSupabase<FxEconomicCalendarRow[]>((sb) =>
    sb
      .from('economic_calendar')
      .select(
        'id, external_id, event_date, event_time, country, event_name, category, impact, actual, forecast, prior, event_datetime_utc'
      )
      .gte('event_date', start)
      .lte('event_date', end)
      .order('event_datetime_utc', { ascending: true, nullsFirst: false })
      .order('event_date', { ascending: true })
  );
  return rows ?? [];
}

/**
 * Aggregated broker opinions per event for a given run_date from
 * `fx_events_snapshot`, mentions-descending (most-cited catalysts first).
 * Returns `[]` when unconfigured, no run_date, or none exist.
 */
export async function getEventOpinions(runDate: string): Promise<FxEventSnapshotRow[]> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return [];
  if (!runDate) return [];
  const rows = await querySupabase<FxEventSnapshotRow[]>((sb) =>
    sb
      .from('fx_events_snapshot')
      .select(
        'run_date, event_key, event_name, event_date, calendar_external_id, release_at, category, currencies, mentions, brokers, citations, as_of'
      )
      .eq('run_date', runDate)
      .order('mentions', { ascending: false })
      .order('event_date', { ascending: true })
  );
  return rows ?? [];
}

/* ------------------------------------------------------------------ *
 * P3 — Traceability + Matrix (fx_research_history)
 * ------------------------------------------------------------------ */

const BRIEF_COLUMNS =
  'run_date, source_file, source_url, document_title, broker_name, analyst_names, ' +
  'report_date, trader_relevance, central_thesis, brief_markdown, currency_views, ' +
  'risk_events, macro_themes, positioning_signals';

/** Resolve the ISO start-date `windowDays` before today (UTC), inclusive. */
function windowStart(windowDays: number): string {
  const start = new Date(Date.now() - Math.max(0, windowDays - 1) * 24 * 60 * 60 * 1000);
  return start.toISOString().slice(0, 10);
}

/** Coerce a brief's `currency_views` jsonb into a typed `CurrencyView[]`. */
function asCurrencyViews(raw: unknown): CurrencyView[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((v): v is Record<string, unknown> => Boolean(v) && typeof v === 'object')
    .map((v) => ({
      currency: String(v.currency ?? '').toUpperCase(),
      direction: String(v.direction ?? ''),
      conviction: String(v.conviction ?? ''),
      signal: v.signal != null ? String(v.signal) : undefined,
      rationale: v.rationale != null ? String(v.rationale) : undefined,
      key_facts: Array.isArray(v.key_facts) ? v.key_facts.map((f) => String(f)) : undefined,
      targets: Array.isArray(v.targets) ? (v.targets as unknown[]) : undefined,
    }));
}

/**
 * Research briefs over a recent window (default 14 days), newest run first.
 * Each brief is keyed by (run_date, source_file). Returns `[]` when unconfigured.
 */
export async function getBriefs(windowDays = 14): Promise<FxBriefRow[]> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return [];
  const start = windowStart(windowDays);
  const rows = await querySupabase<FxBriefRow[]>(
    (sb) =>
      sb
        .from('fx_research_history')
        .select(BRIEF_COLUMNS)
        .gte('run_date', start)
        .order('run_date', { ascending: false })
        .order('broker_name', { ascending: true }) as unknown as PromiseLike<{
        data: FxBriefRow[] | null;
        error: unknown;
      }>
  );
  return rows ?? [];
}

/**
 * A single brief identified by its traceability key (run_date, source_file).
 * Used by the slide-over brief panel (?brief=<source_file>). When only
 * `sourceFile` is known, the latest run carrying that file is returned.
 * Returns `null` when unconfigured or not found.
 */
export async function getBrief(
  sourceFile: string,
  runDate?: string | null
): Promise<FxBriefRow | null> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return null;
  if (!sourceFile) return null;
  const rows = await querySupabase<FxBriefRow[]>((sb) => {
    let q = sb.from('fx_research_history').select(BRIEF_COLUMNS).eq('source_file', sourceFile);
    if (runDate) q = q.eq('run_date', runDate);
    return q.order('run_date', { ascending: false }).limit(1) as unknown as PromiseLike<{
      data: FxBriefRow[] | null;
      error: unknown;
    }>;
  });
  return rows?.[0] ?? null;
}

const _RELEVANCE_RANK: Record<string, number> = { high: 3, medium: 2, low: 1 };

/** Pure ordering for the Today briefs slideshow: relevance desc, then breadth
 *  (# of currency_views) desc, then newest report_date desc. Does not mutate. */
export function sortTodayBriefs(briefs: FxBriefRow[]): FxBriefRow[] {
  const rel = (b: FxBriefRow) => _RELEVANCE_RANK[(b.trader_relevance ?? '').toLowerCase()] ?? 0;
  const breadth = (b: FxBriefRow) => asCurrencyViews(b.currency_views).length;
  return [...briefs].sort(
    (a, b) =>
      rel(b) - rel(a) ||
      breadth(b) - breadth(a) ||
      (b.report_date ?? '').localeCompare(a.report_date ?? '')
  );
}

/** Curated trade ideas for a run_date (rank 1 = top). `[]` when unconfigured/empty. */
export async function getTradeIdeas(runDate: string): Promise<FxTradeIdeaRow[]> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return [];
  if (!runDate) return [];
  const rows = await querySupabase<FxTradeIdeaRow[]>((sb) =>
    sb
      .from('fx_trade_ideas_snapshot')
      .select('run_date, rank, pair, direction, title, thesis, catalyst, levels, citations, as_of')
      .eq('run_date', runDate)
      .order('rank', { ascending: true })
  );
  return rows ?? [];
}

/** Today's research briefs for a run_date, pre-sorted for the slideshow. */
export async function getTodayBriefs(runDate: string): Promise<FxBriefRow[]> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return [];
  if (!runDate) return [];
  const rows = await querySupabase<FxBriefRow[]>(
    (sb) =>
      sb
        .from('fx_research_history')
        .select(BRIEF_COLUMNS)
        .eq('run_date', runDate)
        .order('report_date', { ascending: false }) as unknown as PromiseLike<{
      data: FxBriefRow[] | null;
      error: unknown;
    }>
  );
  return sortTodayBriefs(rows ?? []);
}

/** Pure: keep only rows whose local event date matches `todayKey`. */
export function filterEventsToDay(
  events: FxEconomicCalendarRow[],
  todayKey: string
): FxEconomicCalendarRow[] {
  return events.filter((e) => eventLocalDateKey(e) === todayKey);
}

/** Upcoming macro events narrowed to the viewer-local "today". */
export async function getTodayEvents(): Promise<FxEconomicCalendarRow[]> {
  const all = await getUpcomingEvents();
  const todayKey = eventLocalDateKey({ event_datetime_utc: new Date().toISOString(), event_date: '' });
  return filterEventsToDay(all, todayKey);
}

// The extended leg-validity set: the 8 matrix columns + NOK/SEK. A pair is a
// legitimate FX read only if BOTH legs are in this set (mirrors twelve-x
// _EXTENDED_G10). NOK/SEK count as valid legs but never get their own column.
const MATRIX_EXTENDED: readonly string[] = [...MATRIX_COLUMNS, 'NOK', 'SEK'];

/**
 * Map a broker's view `currency` to its Research Matrix column, matching the
 * twelve-x Notion matrix exactly (nodes/publish.py `_board_column`):
 *   - upper/trim, split on "/";
 *   - drop the view if ANY leg is outside the extended set (pairs with an exotic
 *     leg, gold/XAU, DXY, indices, blanks -> no column);
 *   - file under the BASE (numerator) currency only — NO pair decomposition and
 *     NO direction flip ("EUR/USD bullish" -> EUR column, shown verbatim);
 *   - the base must itself be one of the 8 columns (e.g. NOK/SEK -> dropped).
 */
export function boardColumn(currency: string): MatrixColumn | null {
  const parts = currency.toUpperCase().trim().split('/');
  if (parts.some((p) => !MATRIX_EXTENDED.includes(p))) return null;
  const base = parts[0];
  return (MATRIX_COLUMNS as readonly string[]).includes(base) ? (base as MatrixColumn) : null;
}

/**
 * PURE — assemble the broker×G10 matrix from a set of briefs. For each (broker,
 * board-column) cell, deduplicate exact (source_file, run_date) pairs, sort
 * newest-first, and split into primary + history. Exported for direct testing.
 */
export function assembleMatrix(briefs: FxBriefRow[]): MatrixCell[] {
  if (briefs.length === 0) return [];

  // ISO `YYYY-MM-DD` strings compare lexicographically == chronologically, so a
  // plain `>` is an explicit "is newer" test (run_date first, report_date tiebreak).
  const isNewer = (a: MatrixCell | MatrixCellHistoryEntry, b: MatrixCell | MatrixCellHistoryEntry): boolean => {
    if (a.run_date !== b.run_date) return a.run_date > b.run_date;
    return (a.report_date ?? '') > (b.report_date ?? '');
  };

  // Collect ALL candidate cells per (broker, column) — not just the newest.
  const byCell = new Map<string, MatrixCell[]>();
  for (const b of briefs) {
    const broker = (b.broker_name ?? '').trim();
    if (!broker) continue;
    for (const v of asCurrencyViews(b.currency_views)) {
      if (!v.currency || !v.direction) continue;
      const column = boardColumn(v.currency);
      if (!column) continue; // not a G10-mappable instrument — omitted from the grid
      const key = `${broker}|${column}`;
      const candidate: MatrixCell = {
        broker,
        column,
        currency: v.currency, // verbatim instrument (e.g. "EUR/USD") for display
        direction: v.direction,
        conviction: v.conviction,
        signal: v.signal,
        run_date: b.run_date,
        report_date: b.report_date,
        source_file: b.source_file,
        rationale: v.rationale,
        key_facts: v.key_facts,
        targets: v.targets,
      };
      const list = byCell.get(key) ?? [];
      list.push(candidate);
      byCell.set(key, list);
    }
  }

  // For each (broker, column), deduplicate by (source_file, run_date), sort
  // newest-first, and split into primary + history.
  const result: MatrixCell[] = [];
  for (const [_key, candidates] of byCell.entries()) {
    // Deduplicate: keep first occurrence of each (source_file, run_date) pair.
    const seen = new Set<string>();
    const distinct = candidates.filter((c) => {
      const briefKey = `${c.source_file}|${c.run_date}`;
      if (seen.has(briefKey)) return false;
      seen.add(briefKey);
      return true;
    });

    // Sort newest-first.
    distinct.sort((a, b) => (isNewer(a, b) ? -1 : isNewer(b, a) ? 1 : 0));

    if (distinct.length === 0) continue;

    // Primary = newest; history = rest (already newest-first).
    const primary = distinct[0];
    if (distinct.length > 1) {
      primary.history = distinct.slice(1).map((c) => ({
        run_date: c.run_date,
        report_date: c.report_date,
        source_file: c.source_file,
        direction: c.direction,
        conviction: c.conviction,
        signal: c.signal,
        rationale: c.rationale,
        key_facts: c.key_facts,
        targets: c.targets,
      }));
    }
    result.push(primary);
  }
  return result;
}

/**
 * The broker x G10-currency matrix — the SAME consolidation the twelve-x Notion
 * "Research Matrix" uses, so the two surfaces agree. The LATEST currency_view per
 * (broker, board-column) over a recent window (default 14 days), filed under its
 * base G10 currency via boardColumn (pairs land under the numerator; non-G10 /
 * non-currency instruments are dropped). Newest brief (run_date, then report_date)
 * wins per cell. Returns `[]` when unconfigured.
 */
export async function getMatrix(windowDays = 14): Promise<MatrixCell[]> {
  const briefs = await getBriefs(windowDays);
  return assembleMatrix(briefs);
}

/* ------------------------------------------------------------------ *
 * P4 — Observability (fx_relevance_ledger)
 * ------------------------------------------------------------------ */

const LEDGER_COLUMNS =
  'run_date, source_file, view_index, broker_name, currency, direction, conviction, ' +
  'report_date, w_time, w_event, w_review, relevance, classification, reason, as_of';

/** Resolve the latest run_date present in `fx_relevance_ledger`, or `null`. */
export async function getLatestLedgerDate(): Promise<string | null> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return null;
  const latest = await querySupabase<{ run_date: string }[]>((sb) =>
    sb
      .from('fx_relevance_ledger')
      .select('run_date')
      .order('run_date', { ascending: false })
      .limit(1)
  );
  return latest?.[0]?.run_date ?? null;
}

/**
 * The relevance-ledger rows for a run_date (the deliberation audit), ordered by
 * relevance descending. Defaults to the latest run in the table when `runDate`
 * is omitted. Returns `[]` when unconfigured or none exist.
 *
 * NOTE: genuine errors propagate (querySupabase rethrows once the retry budget
 * is exhausted) — they are NOT swallowed here. The CLIENT owns surfacing a
 * `ledgerError` to the user; do not catch-and-empty in this layer.
 */
export async function getLedger(runDate?: string | null): Promise<FxLedgerRow[]> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return [];
  const date = runDate ?? (await getLatestLedgerDate());
  if (!date) return [];
  const rows = await querySupabase<FxLedgerRow[]>(
    (sb) =>
      sb
        .from('fx_relevance_ledger')
        .select(LEDGER_COLUMNS)
        .eq('run_date', date)
        .order('relevance', { ascending: false })
        .order('broker_name', { ascending: true }) as unknown as PromiseLike<{
        data: FxLedgerRow[] | null;
        error: unknown;
      }>
  );
  return rows ?? [];
}

/* ------------------------------------------------------------------ *
 * P5 — Intelligence "why" drill-down (confluence × consensus × ledger)
 * ------------------------------------------------------------------ */

/** The base (numerator) currency of an instrument; "EUR/USD" → "EUR". */
function baseCurrency(currency: string): string {
  return currency.toUpperCase().trim().split('/')[0];
}

/** Numeric coercion that yields `null` for non-finite/garbage jsonb values. */
function numOrNull(v: unknown): number | null {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Numeric coercion to a finite number, falling back to 0 for the [0,1] legs. */
function num(v: unknown): number {
  return numOrNull(v) ?? 0;
}

/** Extract the Tier-1 score legs + metadata from a confluence `components` jsonb. */
function extractWhyComponents(raw: unknown): IntelligenceWhyComponents {
  const c = raw && typeof raw === 'object' && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const tf = c.timeframe;
  return {
    consensus_strength: num(c.consensus_strength),
    event_alignment: num(c.event_alignment),
    recency: num(c.recency),
    breadth: num(c.breadth),
    n_brokers: numOrNull(c.n_brokers),
    days_to_catalyst: numOrNull(c.days_to_catalyst),
    timeframe: typeof tf === 'string' && tf.trim() ? tf : null,
  };
}

/** Project a canonical consensus row down to the Tier-2 decomposition view. */
function toWhyConsensus(r: FxConsensusSnapshotRow): IntelligenceWhyConsensus {
  return {
    score: r.score,
    confidence: r.confidence,
    agreement: r.agreement,
    tilt: r.tilt,
    n_eff: r.n_eff,
    n_brokers: r.n_brokers,
    n_views: r.n_views,
    bullish_pct: r.bullish_pct,
    bearish_pct: r.bearish_pct,
    neutral_pct: r.neutral_pct,
    watch_pct: r.watch_pct,
  };
}

/**
 * PURE — assemble the Intelligence "why" payload by joining, per confluence
 * idea, the three persisted sources on the idea's BASE currency:
 *   - Tier 1: the score legs in the idea's `components` jsonb;
 *   - Tier 2: the canonical consensus decomposition row for that currency
 *             (callers pass already-filtered medium/weighted rows);
 *   - Tier 3: the supporting `fx_relevance_ledger` desks for that currency,
 *             ordered by relevance descending.
 *
 * Deliberately drops `w_time`/`w_event` from the desk projection — they are
 * effectively constant (≈1.0) and not independently meaningful; only the final
 * product weight `relevance` is surfaced. Items preserve confluence rank order.
 */
export function assembleIntelligenceWhy(
  confluence: FxConfluenceSnapshotRow[],
  consensus: FxConsensusSnapshotRow[],
  ledger: FxLedgerRow[],
  runDate: string | null
): IntelligenceWhy {
  // Index the consensus rows by currency (last write wins; callers pre-filter
  // to the canonical medium/weighted set, one row per currency).
  const consensusByCcy = new Map<string, FxConsensusSnapshotRow>();
  for (const r of consensus) consensusByCcy.set(r.currency.toUpperCase(), r);

  // Bucket ledger desks by currency.
  const desksByCcy = new Map<string, IntelligenceWhyDesk[]>();
  for (const row of ledger) {
    const ccy = row.currency.toUpperCase();
    const desk: IntelligenceWhyDesk = {
      broker: row.broker_name ?? '—',
      classification: row.classification,
      relevance: row.relevance,
      conviction: row.conviction,
      direction: row.direction,
      reason: row.reason,
    };
    const bucket = desksByCcy.get(ccy);
    if (bucket) bucket.push(desk);
    else desksByCcy.set(ccy, [desk]);
  }

  const items: IntelligenceWhyItem[] = [...confluence]
    .sort((a, b) => a.rank - b.rank)
    .map((idea) => {
      const base = baseCurrency(idea.currency);
      const cons = consensusByCcy.get(base) ?? null;
      const desks = (desksByCcy.get(base) ?? []).slice().sort((a, b) => b.relevance - a.relevance);
      return {
        currency: idea.currency,
        rank: idea.rank,
        direction: idea.direction,
        title: idea.title,
        score: idea.score,
        components: extractWhyComponents(idea.components),
        consensus: cons ? toWhyConsensus(cons) : null,
        desks,
      };
    });

  return { runDate, items };
}

/**
 * The assembled Intelligence "why" payload for a run_date (defaults to the
 * latest confluence run). Fetches the confluence ideas, the canonical
 * (medium/weighted) consensus rows, and the relevance-ledger desks for that
 * run, then joins them via `assembleIntelligenceWhy`. Returns an empty payload
 * when unconfigured or no confluence exists.
 */
export async function getIntelligenceWhy(
  runDate?: string,
  limit = 24
): Promise<IntelligenceWhy> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return { runDate: null, items: [] };
  const date = runDate ?? (await getLatestConfluenceDate());
  if (!date) return { runDate: null, items: [] };

  const [confluence, consensus, ledger] = await Promise.all([
    getIntelligence(date, limit),
    // Canonical Tier-2 source: medium-horizon, weighted (mirrors getLatestConsensus's
    // filter), pinned to this run_date so the decomposition matches the idea's run.
    querySupabase<FxConsensusSnapshotRow[]>((sb) =>
      sb
        .from('fx_consensus_snapshot')
        .select(
          'run_date, currency, weighted, score, confidence, agreement, tilt, n_eff, n_brokers, n_views, bullish_pct, bearish_pct, neutral_pct, watch_pct, as_of, timeframe, horizon_weeks'
        )
        .eq('weighted', true)
        .eq('timeframe', 'medium')
        .eq('run_date', date)
    ),
    getLedger(date),
  ]);

  return assembleIntelligenceWhy(confluence, consensus ?? [], ledger, date);
}

/* ------------------------------------------------------------------ *
 * Catalyst resolution + event-time helpers (PURE)
 * ------------------------------------------------------------------ */

/**
 * PURE — resolve the catalyst a confluence idea hangs on against the events
 * feed. Honors an explicit `event_key` in the idea's components; otherwise
 * heuristically matches the earliest upcoming event touching the idea's base
 * currency (in which case `eventKey` stays null so the UI can hedge wording).
 */
export function resolveCatalyst(
  idea: FxConfluenceSnapshotRow,
  events: FxEventSnapshotRow[]
): ConfluenceCatalyst {
  const comp = (idea.components ?? {}) as Record<string, unknown>;
  const dtc = typeof comp.days_to_catalyst === 'number' ? comp.days_to_catalyst : null;
  const explicitKey = typeof comp.event_key === 'string' ? comp.event_key : null;
  const ccy = idea.currency.toUpperCase().split('/')[0];

  let match: FxEventSnapshotRow | undefined;
  if (explicitKey) {
    match = events.find((e) => e.event_key === explicitKey);
  } else {
    const candidates = events
      .filter((e) => {
        const currencies = Array.isArray(e.currencies) ? (e.currencies as unknown[]) : [];
        return currencies.some((c) => String(c).toUpperCase() === ccy);
      })
      .sort((a, b) => (a.event_date ?? '').localeCompare(b.event_date ?? ''));
    match = candidates[0];
  }

  if (!match) {
    return {
      eventKey: null,
      eventName: null,
      eventDate: null,
      calendarExternalId: null,
      daysToCatalyst: dtc,
    };
  }

  return {
    eventKey: explicitKey ? match.event_key : null,
    eventName: match.event_name,
    eventDate: match.event_date,
    calendarExternalId: match.calendar_external_id,
    daysToCatalyst: dtc,
  };
}

/** PURE — the absolute release instant of an event, or null when unparseable. */
export function eventInstant(row: { event_datetime_utc: string | null }): Date | null {
  if (!row.event_datetime_utc) return null;
  const d = new Date(row.event_datetime_utc);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** PURE — whether an event has a resolved absolute release time. */
export function hasResolvedTime(row: { event_datetime_utc: string | null }): boolean {
  return eventInstant(row) != null;
}

/**
 * PURE — the LOCAL calendar day an event falls on. When an absolute instant is
 * present, its local YYYY-MM-DD; otherwise the feed's wall-clock `event_date`.
 */
export function eventLocalDateKey(row: {
  event_datetime_utc: string | null;
  event_date: string;
}): string {
  const inst = eventInstant(row);
  if (!inst) return row.event_date;
  return new Intl.DateTimeFormat('en-CA', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(inst);
}
