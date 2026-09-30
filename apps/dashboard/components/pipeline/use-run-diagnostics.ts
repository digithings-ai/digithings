'use client';

import { useEffect, useState } from 'react';
import { fetchResearchRunDiagnosticsResult } from '@/lib/observability-queries';
import type { PipelineScope } from '@/lib/pipelines';
import type { ResearchRunDiagnostics } from '@/lib/types';

export interface RunDiagnosticsState {
  diagnostics: ResearchRunDiagnostics[] | null;
  loading: boolean;
  /** The read failed (outage / not configured). Distinct from a successful read with no rows. */
  unavailable?: boolean;
}

/**
 * run_health rows (recent window, not filtered by date server-side). Fetched once
 * per scope; consumers filter by run_date. `enabled=false` skips the fetch so a
 * component can accept the state from a parent instead.
 */
export function useRunDiagnostics(scope?: PipelineScope, enabled = true): RunDiagnosticsState {
  const [state, setState] = useState<RunDiagnosticsState>({ diagnostics: null, loading: true });
  const pipelineId = scope?.pipelineId;

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    // Initial `loading` is already true; writes stay in async callbacks.
    fetchResearchRunDiagnosticsResult(pipelineId ? { pipelineId } : undefined)
      .then((r) => alive && setState({ diagnostics: r.rows, loading: false, unavailable: !r.ok }))
      .catch(() => alive && setState({ diagnostics: [], loading: false, unavailable: true }));
    return () => {
      alive = false;
    };
  }, [pipelineId, enabled]);

  return state;
}
