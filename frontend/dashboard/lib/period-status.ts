import { supabaseHouse as supabase } from './supabase';
import { PUBLIC_PERIOD_STATUS_VIEW } from './accounting-views';
import type { ViewRow } from './database.types';

export type PeriodStatusRow = ViewRow<'public_accounting_period_status'>;

export type PeriodStatusLoad =
  | { kind: 'ok'; rows: PeriodStatusRow[] }
  | { kind: 'empty' }
  | { kind: 'query_failed'; message: string }
  | { kind: 'unconfigured' };

const PERIOD_LIMIT = 120;

/**
 * Curated tip status for anon olympus (#2652 / migration 074).
 * Prefer this over raw `olympus_accounting_*` (service_role-only).
 */
export async function fetchPeriodStatusRows(): Promise<PeriodStatusLoad> {
  if (!supabase) return { kind: 'unconfigured' };
  try {
    const { data, error } = await supabase
      .from(PUBLIC_PERIOD_STATUS_VIEW)
      .select(
        'date,status,quality_reasons,opening_equity,closing_equity,day_return_pct,benchmark_symbol,benchmark_return_pct,contract'
      )
      .order('date', { ascending: false })
      .limit(PERIOD_LIMIT);
    if (error) {
      return { kind: 'query_failed', message: error.message };
    }
    const rows = (data ?? []) as PeriodStatusRow[];
    if (!rows.length) return { kind: 'empty' };
    return { kind: 'ok', rows };
  } catch (err) {
    return {
      kind: 'query_failed',
      message: err instanceof Error ? err.message : 'Period status query failed',
    };
  }
}

export function periodStatusLabel(status: string): string {
  switch (status) {
    case 'final':
      return 'Final';
    case 'estimated':
      return 'Estimated';
    case 'incomplete':
      return 'Incomplete';
    case 'failed':
      return 'Failed';
    default:
      return status;
  }
}
