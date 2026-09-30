import { BASELINE_SCOPE, type PipelineScope } from './pipelines';

/**
 * Tables that carry a `pipeline_id` column. EMPTY today: no pipeline/profile
 * column exists on documents, daily_snapshots, run_health or run_event_trace
 * (backend contract open, see DASHBOARD_REBUILD_PLAN section 3). Add a table
 * here only once its column ships; until then every scope reads identically.
 */
export const PIPELINE_SCOPED_TABLES: Set<string> = new Set<string>();

/** The filter a scope adds to a read of `table`, or null (baseline / unscoped table). */
export function scopeFilter(
  table: string,
  scope: PipelineScope = BASELINE_SCOPE,
): { column: 'pipeline_id'; value: string } | null {
  if (scope.pipelineId === BASELINE_SCOPE.pipelineId) return null;
  if (!PIPELINE_SCOPED_TABLES.has(table)) return null;
  return { column: 'pipeline_id', value: scope.pipelineId };
}

/** Apply a scope to a query builder; a no-op for baseline so baseline reads are unchanged. */
export function applyPipelineScope<Q extends { eq(column: string, value: unknown): Q }>(
  query: Q,
  table: string,
  scope: PipelineScope = BASELINE_SCOPE,
): Q {
  const f = scopeFilter(table, scope);
  return f ? query.eq(f.column, f.value) : query;
}
