import type { PipelineObservabilityBundle } from '@/lib/types';

function s(v: unknown): string {
  return v == null ? '' : String(v);
}

function asObj(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function pushLinesFromList(out: string[], label: string, items: unknown[] | undefined) {
  const arr = Array.isArray(items) ? items.filter((x) => s(x).trim()) : [];
  if (!arr.length) return;
  out.push(`${label}:`, ...arr.map((x) => `• ${s(x).trim()}`));
}

/** Extract exploration + vehicle-map blurbs for one thesis from raw document payloads. */
export function thesisPipelineNarrativeFromPayloads(
  thesisId: string,
  mte: Record<string, unknown> | null,
  tvm: Record<string, unknown> | null
): { exploration: string | null; vehicles: string | null } {
  let exploration: string | null = null;
  if (mte) {
    const body = asObj(mte.body) || asObj(mte);
    const theses = Array.isArray(body?.theses) ? body.theses : [];
    for (const t of theses) {
      const th = asObj(t);
      if (!th || s(th.thesis_id) !== thesisId) continue;
      const lines: string[] = [];
      const title = s(th.title).trim();
      if (title) lines.push(title);
      const stmt = s(th.statement).trim();
      if (stmt) lines.push(stmt);
      pushLinesFromList(lines, 'Tailwinds', th.tailwinds as unknown[]);
      pushLinesFromList(lines, 'Headwinds', th.headwinds as unknown[]);
      pushLinesFromList(lines, 'Bull case', th.bull_case as unknown[]);
      pushLinesFromList(lines, 'Bear case', th.bear_case as unknown[]);
      exploration = lines.length ? lines.join('\n') : null;
      break;
    }
  }

  let vehicles: string | null = null;
  if (tvm) {
    const body = asObj(tvm.body) || asObj(tvm);
    const mappings = Array.isArray(body?.mappings) ? body.mappings : [];
    for (const row of mappings) {
      const m = asObj(row);
      if (!m || s(m.thesis_id) !== thesisId) continue;
      const lines: string[] = [];
      const rat = s(m.rationale).trim();
      if (rat) lines.push(rat);
      const tickers = Array.isArray(m.candidate_tickers) ? m.candidate_tickers.map((x) => s(x)).filter(Boolean) : [];
      if (tickers.length) lines.push(`Candidates: ${tickers.join(', ')}`);
      pushLinesFromList(lines, 'Exclusions', m.exclusion_reasons as unknown[]);
      pushLinesFromList(lines, 'Mandate notes', m.user_mandate_notes as unknown[]);
      vehicles = lines.length ? lines.join('\n') : null;
      break;
    }
  }

  return { exploration, vehicles };
}

/** Narrative snippets when the calendar date matches the loaded dashboard pipeline bundle. */
export function thesisPipelineNarrativeForThesis(
  thesisId: string,
  effHistoryDate: string | null,
  lastUpdated: string | null,
  pipeline: PipelineObservabilityBundle | null
): { exploration: string | null; vehicles: string | null } {
  if (!effHistoryDate || !lastUpdated || effHistoryDate !== lastUpdated || !pipeline) {
    return { exploration: null, vehicles: null };
  }
  return thesisPipelineNarrativeFromPayloads(
    thesisId,
    pipeline.market_thesis_exploration,
    pipeline.thesis_vehicle_map
  );
}
