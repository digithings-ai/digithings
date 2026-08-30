import { isSupabaseConfigured, supabaseHouse as supabase } from './supabase';
import type { ViewRow } from './database.types';

export type PipelineRunEvent = ViewRow<'olympus_run_event_trace'>;

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
        .from('olympus_run_event_trace')
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