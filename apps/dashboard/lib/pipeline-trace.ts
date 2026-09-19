import { isSupabaseConfigured, supabase } from './supabase';
import type { ViewRow } from './database.types';

// Canonical view name after the Phase B/C olympus rename (#4295). Migration 135 drops
// the legacy `olympus_run_event_trace` compat view, so the dashboard must read `run_event_trace`.
export type PipelineRunEvent = ViewRow<'run_event_trace'>;

export type PipelineTraceResult =
  | { state: 'available'; events: PipelineRunEvent[] }
  | { state: 'not-recorded'; events: [] }
  | { state: 'unavailable'; events: [] };

const TRACE_PAGE_SIZE = 1_000;
const TRACE_MAX_ROWS = 10_000;

export function classifyPipelineTrace(
  events: PipelineRunEvent[],
  querySucceeded: boolean,
): PipelineTraceResult {
  if (!querySucceeded) return { state: 'unavailable', events: [] };
  if (events.length === 0) return { state: 'not-recorded', events: [] };
  return { state: 'available', events };
}

/** Read every body-free call event for one run date from the curated public view. */
export async function fetchPipelineTrace(runDate: string): Promise<PipelineTraceResult> {
  if (!isSupabaseConfigured() || !supabase) {
    return { state: 'unavailable', events: [] };
  }

  const events: PipelineRunEvent[] = [];
  try {
    for (let offset = 0; offset < TRACE_MAX_ROWS; offset += TRACE_PAGE_SIZE) {
      const { data, error } = await supabase
        .from('run_event_trace')
        .select('*')
        .eq('run_date', runDate)
        .order('run_id', { ascending: true })
        .order('attempt', { ascending: true })
        .order('sequence', { ascending: true })
        .range(offset, offset + TRACE_PAGE_SIZE - 1);
      if (error) return classifyPipelineTrace([], false);

      const page = data ?? [];
      events.push(...page);
      if (page.length < TRACE_PAGE_SIZE) break;
    }
  } catch {
    return classifyPipelineTrace([], false);
  }
  return classifyPipelineTrace(events, true);
}