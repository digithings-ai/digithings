/**
 * Observability dashboard data access (Pillar 3D).
 *
 * Reads the four read-only surfaces the observability route needs — `decision_log`,
 * `position_attribution`, the curated `atlas_run_health` view, and the latest `positions`
 * (with advisory risk fields). Kept separate from `getFullDashboardData` so the main Morning
 * Read bundle stays lean; this fires only when the observability route mounts.
 *
 * Every query is FAIL-SOFT: a missing/forbidden source (e.g. the `atlas_run_health` view
 * before migration 041 is applied, or an empty book) resolves to an empty result rather than
 * throwing, so the dashboard renders a clean empty state instead of an error wall.
 */

import { supabase, isSupabaseConfigured } from './supabase';
import type { TableRow, ViewRow } from './database.types';
import type { AtlasRunDiagnostics } from './types';

const RUN_HEALTH_LIMIT = 30;
const DECISION_LIMIT = 1000;
const ATTRIBUTION_LIMIT = 600;
const POSITIONS_LIMIT = 400;

export interface ObservabilityData {
  decisions: TableRow<'decision_log'>[];
  runHealth: ViewRow<'atlas_run_health'>[];
  attribution: TableRow<'position_attribution'>[]; // latest date only
  attributionDate: string | null;
  positions: TableRow<'positions'>[]; // latest date only
  positionsDate: string | null;
  runHealthAvailable: boolean; // false when the 041 view isn't applied yet
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

/** Keep only the rows belonging to the most-recent `date` present (the latest snapshot). */
function latestDateRows<T extends { date: string | null }>(rows: T[]): { rows: T[]; date: string | null } {
  let max: string | null = null;
  for (const r of rows) {
    if (r.date && (max === null || r.date > max)) max = r.date;
  }
  return { rows: max === null ? [] : rows.filter((r) => r.date === max), date: max };
}

export async function fetchObservabilityData(): Promise<ObservabilityData> {
  // Distinguish a total misconfiguration (no Supabase env) from a configured-but-empty book:
  // throw so the page shows a clear error, matching the main data layer (lib/queries.ts).
  // Per-query failures below still fail-soft (a missing 041 view degrades, not errors).
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY). ' +
        'Observability data cannot be loaded.'
    );
  }
  const [decisionsRes, runHealthRes, attributionRes, positionsRes] = await Promise.all([
    safeSelect<TableRow<'decision_log'>>('decision_log', (sb) =>
      sb
        .from('decision_log')
        .select(
          'id,run_id,run_date,ticker,stance,conviction,thesis,benchmark,holding_days,status,actual_return,alpha,reflection,resolved_at,created_at'
        )
        .order('run_date', { ascending: false })
        .limit(DECISION_LIMIT)
    ),
    safeSelect<ViewRow<'atlas_run_health'>>('atlas_run_health', (sb) =>
      sb
        .from('atlas_run_health')
        .select(
          'run_id,run_date,run_type,model,status,started_at,finished_at,duration_s,segments_total,segments_ok,segments_carried,segments_failed,created_at'
        )
        // Order by created_at (NOT NULL, DEFAULT now()): run_date is nullable, so ordering by
        // it could surface a NULL-dated row first and make runHealth[0] point at the wrong run.
        .order('created_at', { ascending: false })
        .limit(RUN_HEALTH_LIMIT)
    ),
    safeSelect<TableRow<'position_attribution'>>('position_attribution', (sb) =>
      sb
        .from('position_attribution')
        .select('*')
        .order('date', { ascending: false })
        .limit(ATTRIBUTION_LIMIT)
    ),
    safeSelect<TableRow<'positions'>>('positions', (sb) =>
      sb.from('positions').select('*').order('date', { ascending: false }).limit(POSITIONS_LIMIT)
    ),
  ]);

  const attribution = latestDateRows(attributionRes.rows);
  const positions = latestDateRows(positionsRes.rows);

  return {
    decisions: decisionsRes.rows,
    runHealth: runHealthRes.rows,
    attribution: attribution.rows,
    attributionDate: attribution.date,
    positions: positions.rows,
    positionsDate: positions.date,
    runHealthAvailable: runHealthRes.ok,
  };
}

const RUN_DIAGNOSTICS_LIMIT = 30;

/** Lift cached_tokens out of the breakdown jsonb (top-level or by_kind.chat). */
function cachedTokensOf(breakdown: unknown): number | null {
  if (!breakdown || typeof breakdown !== 'object') return null;
  const b = breakdown as Record<string, unknown>;
  if (typeof b.cached_tokens === 'number') return b.cached_tokens;
  const byKind = b.by_kind as Record<string, unknown> | undefined;
  const chat = byKind?.chat as Record<string, unknown> | undefined;
  return typeof chat?.cached_tokens === 'number' ? chat.cached_tokens : null;
}

/**
 * Read run economics directly from `atlas_run_diagnostics` (D3) — cost, tokens,
 * cache-hit, grounding, per-phase breakdown — bypassing the stripping
 * `atlas_run_health` view. Fail-soft: empty array on missing source / RLS deny.
 */
export async function fetchAtlasRunDiagnostics(): Promise<AtlasRunDiagnostics[]> {
  const res = await safeSelect<TableRow<'atlas_run_diagnostics'>>('atlas_run_diagnostics', (sb) =>
    sb
      .from('atlas_run_diagnostics')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(RUN_DIAGNOSTICS_LIMIT)
  );
  return res.rows.map((r) => ({
    run_id: r.run_id,
    run_type: r.run_type,
    run_date: r.run_date,
    model: r.model,
    status: r.status,
    started_at: r.started_at,
    finished_at: r.finished_at,
    duration_s: r.duration_s,
    llm_calls: r.llm_calls,
    prompt_tokens: r.prompt_tokens,
    completion_tokens: r.completion_tokens,
    total_tokens: r.total_tokens,
    cached_tokens: cachedTokensOf(r.breakdown),
    search_calls: r.search_calls,
    grounding_ok: r.grounding_ok,
    grounding_failed: r.grounding_failed,
    est_cost_usd: r.est_cost_usd,
    segments_total: r.segments_total,
    segments_ok: r.segments_ok,
    segments_carried: r.segments_carried,
    segments_failed: r.segments_failed,
    error_summary: r.error_summary,
    breakdown: (r.breakdown ?? null) as Record<string, unknown> | null,
    created_at: r.created_at,
  }));
}
