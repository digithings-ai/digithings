/**
 * LOCKED deep-link grammar for the Pipeline hub (Surface 1).
 * `/pipeline?date=YYYY-MM-DD&stage=<stage>&node=<document_key>`
 * "open day D, expand stage S, focus node N." Keyed off `document_key`, NOT the
 * legacy `path` field. Six consumers depend on this exact shape; do not drift.
 */
export type PipelineStage = 'inputs' | 'research' | 'synthesis' | 'selection' | 'decision';

export function buildPipelineHref(opts: {
  date?: string | null;
  stage?: PipelineStage | null;
  node?: string | null;
}): string {
  const p = new URLSearchParams();
  if (opts.date) p.set('date', opts.date);
  if (opts.stage) p.set('stage', opts.stage);
  if (opts.node) p.set('node', opts.node);
  const qs = p.toString();
  return qs ? `/pipeline?${qs}` : '/pipeline';
}

/** Map a `document_key` to the stage that owns it (per the spec topology table). */
export function stageForDocumentKey(documentKey: string): PipelineStage | null {
  const k = documentKey.toLowerCase();
  if (k === 'digest') return 'synthesis';
  if (k.startsWith('analyst/') || k.startsWith('deliberation/')) return 'selection';
  if (k === 'pm-direction-memo' || k === 'pm-rebalance' || k === 'risk-debate') return 'selection';
  if (k.startsWith('commit-run/')) return 'decision';
  if (
    k.startsWith('alt-') ||
    k.startsWith('inst-') ||
    k.startsWith('sector-') ||
    k === 'macro' ||
    ['bonds', 'commodities', 'forex', 'crypto', 'equity', 'international'].includes(k)
  ) {
    return 'research';
  }
  if (k === 'preflight' || k.startsWith('market-data')) return 'inputs';
  return null;
}
