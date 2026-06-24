/**
 * Observability dashboard data access (Pillar 3D).
 *
 * Reads the decision track record (`decision_log`) the Decision Scorecard needs, plus
 * — via `fetchAtlasRunDiagnostics` — the run economics the System surface reads directly
 * from `atlas_run_diagnostics`. Kept separate from `getFullDashboardData` so the main
 * Morning Read bundle stays lean; these fire only when their consumer mounts.
 *
 * Attribution and per-position risk now live on Performance/Holdings (which read their own
 * sources), and System reads run telemetry straight from `atlas_run_diagnostics` — so the
 * stripping `atlas_run_health` view is no longer read here.
 *
 * Every query is FAIL-SOFT: a missing/forbidden source (e.g. an empty book) resolves to an
 * empty result rather than throwing, so consumers render a clean empty state instead of an
 * error wall.
 */

import { supabase, isSupabaseConfigured } from './supabase';
import type { TableRow } from './database.types';
import type { AtlasRunDiagnostics } from './types';

const DECISION_LIMIT = 1000;

export interface ObservabilityData {
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

export async function fetchObservabilityData(): Promise<ObservabilityData> {
  // Distinguish a total misconfiguration (no Supabase env) from a configured-but-empty book:
  // throw so the page shows a clear error, matching the main data layer (lib/queries.ts).
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY). ' +
        'Observability data cannot be loaded.'
    );
  }
  const decisionsRes = await safeSelect<TableRow<'decision_log'>>('decision_log', (sb) =>
    sb
      .from('decision_log')
      .select(
        'id,run_id,run_date,ticker,stance,conviction,thesis,benchmark,holding_days,status,actual_return,alpha,reflection,resolved_at,created_at'
      )
      .order('run_date', { ascending: false })
      .limit(DECISION_LIMIT)
  );
  return { decisions: decisionsRes.rows };
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
