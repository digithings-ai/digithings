import type { WaterfallTraceRow } from '@digithings/ui/ui';
import type { PipelineStage } from './pipeline-links';
import type { PipelineRunEvent } from './pipeline-trace';
import { stageForTraceEvent, TRACE_STAGE_COVERAGE, traceStageLabel } from './pipeline-trace-stage';

const STAGE_ORDER: readonly PipelineStage[] = ['inputs', 'research', 'synthesis', 'selection', 'decision', 'learning'];

/** Per-stage cap on drill-down rows (slowest first) so 10k-call days stay legible. */
export const TIMELINE_KEYS_PER_STAGE = 5;

export interface PipelineTimeline {
  rows: WaterfallTraceRow[];
  /** Row id -> document_key, for rows a click can open. */
  keyById: Record<string, string>;
  /** Total span in ms. */
  totalMs: number;
  calls: number;
  retries: number;
  errors: number;
  /** How bars were placed: real timestamps, or cumulative durations in sequence order. */
  basis: 'created_at' | 'sequence' | 'none';
  /** Events that mapped to no stage (not drawn). */
  unmapped: number;
}

interface Placed {
  event: PipelineRunEvent;
  stage: PipelineStage;
  start: number;
  end: number;
}

function dur(e: PipelineRunEvent): number {
  return typeof e.duration_ms === 'number' && Number.isFinite(e.duration_ms) && e.duration_ms > 0 ? e.duration_ms : 0;
}

function attention(e: PipelineRunEvent): boolean {
  return e.status === 'error' || (e.retry_count ?? 0) > 0;
}

/**
 * Place each event on a time axis. `created_at` is treated as the call END (the
 * row is written on completion) so start = created_at - duration_ms. This is an
 * approximation; when any timestamp is unusable we fall back to cumulative
 * duration in (run, attempt, sequence) order, attempts laid end to end.
 */
function place(events: readonly PipelineRunEvent[]): { placed: Omit<Placed, 'stage'>[]; basis: 'created_at' | 'sequence' | 'none' } {
  if (events.length === 0) return { placed: [], basis: 'none' };
  const ends = events.map((e) => (e.created_at ? Date.parse(e.created_at) : NaN));
  if (ends.every((t) => Number.isFinite(t))) {
    const starts = events.map((e, i) => ends[i] - dur(e));
    const origin = Math.min(...starts);
    return {
      placed: events.map((event, i) => ({ event, start: starts[i] - origin, end: ends[i] - origin })),
      basis: 'created_at',
    };
  }
  const order = events
    .map((event, i) => ({ event, i }))
    .sort(
      (a, b) =>
        String(a.event.run_id).localeCompare(String(b.event.run_id)) ||
        (a.event.attempt ?? 0) - (b.event.attempt ?? 0) ||
        (a.event.sequence ?? 0) - (b.event.sequence ?? 0),
    );
  let cursor = 0;
  const out: Omit<Placed, 'stage'>[] = [];
  for (const { event } of order) {
    out.push({ event, start: cursor, end: cursor + dur(event) });
    cursor += dur(event);
  }
  return { placed: out, basis: 'sequence' };
}

export function buildPipelineTimeline(
  events: readonly PipelineRunEvent[],
  keysPerStage: number = TIMELINE_KEYS_PER_STAGE,
): PipelineTimeline {
  const { placed: raw, basis } = place(events);
  const placed: Placed[] = [];
  let unmapped = 0;
  for (const p of raw) {
    const stage = stageForTraceEvent(p.event);
    if (stage) placed.push({ ...p, stage });
    else unmapped++;
  }

  const rows: WaterfallTraceRow[] = [];
  const keyById: Record<string, string> = {};
  let totalMs = 0;
  for (const p of placed) totalMs = Math.max(totalMs, p.end);

  for (const stage of STAGE_ORDER) {
    const inStage = placed.filter((p) => p.stage === stage);
    const label = traceStageLabel(stage);
    if (inStage.length === 0) {
      const gap = TRACE_STAGE_COVERAGE[stage] === 'typed-gap';
      rows.push({
        id: `stage:${stage}`,
        label: `${label} · ${gap ? 'no calls emitted' : 'no calls recorded'}`,
        start: 0,
        duration: 0,
        status: 'mute',
        depth: 0,
      });
      continue;
    }
    const start = Math.min(...inStage.map((p) => p.start));
    const end = Math.max(...inStage.map((p) => p.end));
    rows.push({
      id: `stage:${stage}`,
      label: `${label} · ${inStage.length} calls`,
      start,
      duration: end - start,
      status: inStage.some((p) => attention(p.event)) ? 'warn' : 'ok',
      depth: 0,
    });

    const groups = new Map<string, Placed[]>();
    for (const p of inStage) {
      const k = p.event.document_key ?? p.event.name ?? p.event.phase ?? 'call';
      const arr = groups.get(k) ?? [];
      arr.push(p);
      groups.set(k, arr);
    }
    const top = [...groups.entries()]
      .map(([k, g]) => {
        const s = Math.min(...g.map((p) => p.start));
        const e = Math.max(...g.map((p) => p.end));
        return { k, g, s, e };
      })
      .sort((a, b) => b.e - b.s - (a.e - a.s))
      .slice(0, keysPerStage)
      .sort((a, b) => a.s - b.s);
    for (const t of top) {
      const id = `key:${stage}:${t.k}`;
      const hasDocKey = t.g.some((p) => p.event.document_key === t.k);
      if (hasDocKey) keyById[id] = t.k;
      rows.push({
        id,
        label: t.g.length > 1 ? `${t.k} ×${t.g.length}` : t.k,
        start: t.s,
        duration: t.e - t.s,
        status: t.g.some((p) => attention(p.event)) ? 'warn' : 'ok',
        depth: 1,
      });
    }
  }

  return {
    rows,
    keyById,
    totalMs,
    calls: placed.length,
    retries: placed.reduce((n, p) => n + (p.event.retry_count ?? 0), 0),
    errors: placed.filter((p) => p.event.status === 'error').length,
    basis,
    unmapped,
  };
}

export function formatMs(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return '0s';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s < 10 ? s.toFixed(1) : Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const r = Math.round(s % 60);
  return r ? `${m}m ${r}s` : `${m}m`;
}

/** Header counts for the timeline: says 'N placed of M' when some events map to no stage. */
export function timelineCallsLabel(t: Pick<PipelineTimeline, 'calls' | 'unmapped'>): string {
  return t.unmapped > 0 ? `${t.calls} placed of ${t.calls + t.unmapped} calls` : `${t.calls} calls`;
}
