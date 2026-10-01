/**
 * Pipeline registry. Only the baseline exists today; user pipelines and forks
 * will arrive from a fetched list later, so consumers go through `usePipelines()`
 * and a `PipelineScope` instead of assuming a single backend.
 */
export interface PipelineRef {
  id: string;
  label: string;
  kind: 'baseline' | 'user' | 'fork';
}

/** What data fetchers take to read one pipeline's runs (optional; defaults to baseline). */
export interface PipelineScope {
  pipelineId: string;
}

export const BASELINE_PIPELINE: PipelineRef = { id: 'baseline', label: 'Baseline', kind: 'baseline' };
export const BASELINE_SCOPE: PipelineScope = { pipelineId: BASELINE_PIPELINE.id };

const STATIC_PIPELINES: readonly PipelineRef[] = [BASELINE_PIPELINE];

/** Static today; swap for a fetched list without touching consumers. */
export function usePipelines(): readonly PipelineRef[] {
  return STATIC_PIPELINES;
}

/** Unknown ids fall back to baseline. */
export function resolvePipelineId(id: string | null | undefined, list: readonly PipelineRef[] = STATIC_PIPELINES): string {
  return list.some((p) => p.id === id) ? (id as string) : BASELINE_PIPELINE.id;
}

/**
 * Append `pipeline=<id>` to a query string; omitted for baseline so existing URLs
 * are unchanged.
 */
export function withPipelineParam(search: string, pipelineId: string): string {
  const params = new URLSearchParams(search);
  if (pipelineId === BASELINE_PIPELINE.id) params.delete('pipeline');
  else params.set('pipeline', pipelineId);
  const out = params.toString();
  return out ? `?${out}` : '';
}
