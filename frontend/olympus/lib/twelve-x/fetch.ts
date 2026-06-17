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
import type {
  FxConfluenceSnapshotRow,
  FxConsensusSnapshotRow,
  FxDailyDigestRow,
  FxEconomicCalendarRow,
  FxEventSnapshotRow,
} from './types';

/** Run a twelve-x Supabase query with bounded exponential-backoff retries. */
async function querySupabase<T>(
  queryFn: (sb: SupabaseClient) => PromiseLike<{ data: T | null; error: unknown }>,
  { retries = 3, delayMs = 500 }: { retries?: number; delayMs?: number } = {}
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
      if (data === null) throw new Error('No data returned');
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
function normalizeKeyThemes(raw: FxDailyDigestRow['key_themes']): string[] {
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
export async function getConsensusTimeSeries(): Promise<FxConsensusSnapshotRow[]> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return [];
  const rows = await querySupabase<FxConsensusSnapshotRow[]>((sb) =>
    sb
      .from('fx_consensus_snapshot')
      .select(
        'run_date, currency, weighted, score, confidence, agreement, tilt, n_eff, n_brokers, n_views, bullish_pct, bearish_pct, neutral_pct, watch_pct, as_of'
      )
      .eq('weighted', true)
      .order('run_date', { ascending: true })
      .order('currency', { ascending: true })
  );
  return rows ?? [];
}

/**
 * The weighted consensus rows for the latest run_date present in the table
 * (one row per G10 currency). Returns `[]` when twelve-x is unconfigured or the
 * table is empty.
 */
export async function getLatestConsensus(): Promise<FxConsensusSnapshotRow[]> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return [];

  // Resolve the latest run_date first (cheap), then pull that day's full set.
  const latest = await querySupabase<{ run_date: string }[]>((sb) =>
    sb
      .from('fx_consensus_snapshot')
      .select('run_date')
      .eq('weighted', true)
      .order('run_date', { ascending: false })
      .limit(1)
  ).catch(() => [] as { run_date: string }[]);

  const latestDate = latest?.[0]?.run_date;
  if (!latestDate) return [];

  const rows = await querySupabase<FxConsensusSnapshotRow[]>((sb) =>
    sb
      .from('fx_consensus_snapshot')
      .select(
        'run_date, currency, weighted, score, confidence, agreement, tilt, n_eff, n_brokers, n_views, bullish_pct, bearish_pct, neutral_pct, watch_pct, as_of'
      )
      .eq('weighted', true)
      .eq('run_date', latestDate)
      .order('currency', { ascending: true })
  );
  return rows ?? [];
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
      .select('run_date, headline, summary, key_themes, doc_count, broker_count')
      .order('run_date', { ascending: false })
      .limit(1)
  ).catch(() => [] as FxDailyDigestRow[]);

  const row = rows?.[0];
  if (!row) return null;
  return {
    run_date: row.run_date,
    headline: row.headline,
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
  ).catch(() => [] as FxConfluenceSnapshotRow[]);
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
  ).catch(() => [] as { run_date: string }[]);
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
  ).catch(() => [] as FxConfluenceSnapshotRow[]);
  return rows ?? [];
}

/**
 * Upcoming macro catalysts from `fx_economic_calendar`: today → +14 days,
 * ordered by the absolute UTC release instant (NULL release times — all-day rows —
 * sort last, then by event_date). Returns `[]` when unconfigured or none exist.
 */
export async function getUpcomingEvents(): Promise<FxEconomicCalendarRow[]> {
  if (!isTwelveXConfigured() || !twelveXSupabase) return [];
  const today = new Date();
  const start = today.toISOString().slice(0, 10);
  const horizon = new Date(today.getTime() + 14 * 24 * 60 * 60 * 1000);
  const end = horizon.toISOString().slice(0, 10);
  const rows = await querySupabase<FxEconomicCalendarRow[]>((sb) =>
    sb
      .from('fx_economic_calendar')
      .select(
        'id, event_date, event_time, country, event_name, category, impact, actual, forecast, prior, event_datetime_utc'
      )
      .gte('event_date', start)
      .lte('event_date', end)
      .order('event_datetime_utc', { ascending: true, nullsFirst: false })
      .order('event_date', { ascending: true })
  ).catch(() => [] as FxEconomicCalendarRow[]);
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
  ).catch(() => [] as FxEventSnapshotRow[]);
  return rows ?? [];
}
