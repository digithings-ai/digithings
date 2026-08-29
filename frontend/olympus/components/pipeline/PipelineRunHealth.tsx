'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { Skeleton, SkeletonGroup } from '@digithings/web';
import { EmptyState } from '@/components/observability/shared';
import { FreshnessBanner, latestSuccessfulRun } from '@/components/system/freshness-banner';
import { RunEconomicsRow } from '@/components/system/run-economics-row';
import { fetchAtlasRunDiagnostics } from '@/lib/observability-queries';
import type { AtlasRunDiagnostics } from '@/lib/types';

function forDate(diagnostics: AtlasRunDiagnostics[], date: string): AtlasRunDiagnostics[] {
  return diagnostics.filter((d) => d.run_date === date);
}

function summaryLine(dayRuns: AtlasRunDiagnostics[]): string {
  if (!dayRuns.length) return 'No run telemetry for this date';
  const latest = dayRuns[0];
  const segs =
    latest.segments_ok != null && latest.segments_total != null
      ? `${latest.segments_ok}/${latest.segments_total} segments`
      : null;
  const status = latest.status ?? 'unknown';
  return [status, segs].filter(Boolean).join(' · ');
}

/** Collapsible run-health stats for the Pipeline date selector. */
export default function PipelineRunHealth({ date }: { date: string }) {
  const [diagnostics, setDiagnostics] = useState<AtlasRunDiagnostics[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    // Initial `loading` is already true — avoid setState in the effect body
    // (react-hooks/set-state-in-effect). Writes stay in async callbacks.
    fetchAtlasRunDiagnostics()
      .then((d) => alive && setDiagnostics(d))
      .catch(() => alive && setDiagnostics([]))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  const dayRuns = useMemo(
    () => (diagnostics ? forDate(diagnostics, date) : []),
    [diagnostics, date]
  );
  const dayOk = useMemo(() => latestSuccessfulRun(dayRuns), [dayRuns]);
  const summary = loading ? 'Loading…' : summaryLine(dayRuns);

  return (
    <details
      data-testid="pipeline-run-health"
      className="group border-b border-hair bg-surface"
    >
      <summary className="flex cursor-pointer list-none items-center gap-3 px-3 py-2.5 transition-colors hover:bg-ink/[0.02] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50 md:px-4 [&::-webkit-details-marker]:hidden">
        <span className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
          Run health
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] tabular-nums text-ink-soft">
          {date} · {summary}
        </span>
        <ChevronDown
          size={14}
          className="shrink-0 text-ink-mute transition-transform group-open:rotate-180"
          aria-hidden
        />
      </summary>

      <div className="space-y-4 border-t border-hair px-3 py-4 md:px-4">
        {loading ? (
          <SkeletonGroup aria-label="Loading run diagnostics" className="flex flex-col gap-4">
            <Skeleton variant="block" className="h-12 w-full" />
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} variant="block" className="h-16 w-full" />
              ))}
            </div>
          </SkeletonGroup>
        ) : !dayRuns.length ? (
          <EmptyState
            title="No run for this date"
            message="Pick a date with a recorded pipeline run to see duration, segment counts, and carry/fail stats."
          />
        ) : (
          <>
            {dayOk ? (
              <FreshnessBanner latest={dayOk} />
            ) : (
              <div className="rounded-[12px] border border-hair px-4 py-3 text-sm text-warn">
                No successful run on {date} — see segment counts below.
              </div>
            )}
            <RunEconomicsRow latest={dayRuns[0]} />
          </>
        )}
      </div>
    </details>
  );
}
