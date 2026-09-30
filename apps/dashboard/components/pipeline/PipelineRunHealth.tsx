'use client';

import { useMemo } from 'react';
import { ChevronDown } from 'lucide-react';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  CompositionBar,
  EmptyState,
  Skeleton,
  SkeletonGroup,
} from '@digithings/ui/ui';
import { FreshnessBanner, latestSuccessfulRun } from '@/components/system/freshness-banner';
import { EntitledSurface } from '@/components/entitled-surface';
import { buildDayKpis } from '@/lib/pipeline-kpis';
import { groupRunEpisodes } from '@/lib/run-episodes';
import type { PipelineScope } from '@/lib/pipelines';
import type { ResearchRunDiagnostics } from '@/lib/types';
import type { PlanTier } from '@/lib/entitlements';
import PipelineKpiStrip from './PipelineKpiStrip';
import { useRunDiagnostics, type RunDiagnosticsState } from './use-run-diagnostics';

function forDate(diagnostics: ResearchRunDiagnostics[], date: string): ResearchRunDiagnostics[] {
  return diagnostics.filter((d) => d.run_date === date);
}

/** Collapsible run-health panel for the selected date: freshness + KPI tiles + composition bars. */
export default function PipelineRunHealth({
  date,
  tier,
  scope,
  state,
  artifactCount = 0,
}: {
  date: string;
  /** Test override for the economics strip gate. */
  tier?: PlanTier;
  scope?: PipelineScope;
  /** Diagnostics owned by the parent (avoids a second fetch); fetched here when omitted. */
  state?: RunDiagnosticsState;
  artifactCount?: number;
}) {
  const own = useRunDiagnostics(scope, state === undefined);
  const { diagnostics, loading, unavailable = false } = state ?? own;

  const dayRuns = useMemo(() => (diagnostics ? forDate(diagnostics, date) : []), [diagnostics, date]);
  const dayOk = useMemo(() => latestSuccessfulRun(dayRuns), [dayRuns]);
  const kpis = useMemo(
    () => buildDayKpis({ date, episodes: groupRunEpisodes(diagnostics ?? []), artifactCount }),
    [diagnostics, date, artifactCount],
  );
  const segTotal = kpis.segments.total;

  return (
    <Collapsible data-testid="pipeline-run-health" defaultOpen className="group border-b border-hair bg-surface">
      <CollapsibleTrigger className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-ink/[0.02] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50 md:px-4">
        <span className="font-mono text-[0.62rem] font-semibold uppercase tracking-[0.1em] text-ink-mute">
          Run health
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-xs tabular-nums text-ink-soft">
          {date} · {loading
            ? 'Loading…'
            : unavailable
              ? 'Run data unavailable'
              : kpis.hasTelemetry
                ? (kpis.status ?? 'unknown')
                : 'No run telemetry'}
        </span>
        {!loading && !unavailable && segTotal ? (
          <CompositionBar
            mode="stacked"
            total={segTotal}
            height={6}
            className="hidden w-28 shrink-0 md:block"
            label={`Segments: ${kpis.segments.ok ?? 0} ok of ${segTotal}`}
            segments={[
              { key: 'ok', label: 'ok', value: kpis.segments.ok ?? 0, tone: 'accent' },
              { key: 'carried', label: 'carried', value: kpis.segments.carried ?? 0, tone: 'mute' },
              { key: 'failed', label: 'failed', value: kpis.segments.failed ?? 0, tone: 'warn' },
            ]}
          />
        ) : null}
        <ChevronDown
          size={14}
          className="shrink-0 text-ink-mute transition-transform group-data-open:rotate-180"
          aria-hidden
        />
      </CollapsibleTrigger>

      <CollapsibleContent className="space-y-4 border-t border-hair px-3 py-4 md:px-4">
        {loading ? (
          <SkeletonGroup aria-label="Loading run diagnostics" className="flex flex-col gap-4">
            <Skeleton variant="block" className="h-12 w-full" />
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} variant="block" className="h-16 w-full" />
              ))}
            </div>
          </SkeletonGroup>
        ) : unavailable ? (
          <EmptyState
            dress="glass"
            variant="error"
            title="Run data unavailable"
            body="Run telemetry could not be read, so run health is not shown. This is not the same as a date with no run."
          />
        ) : !dayRuns.length ? (
          <EmptyState
            dress="glass"
            data-reveal
            title="No run for this date"
            body="Pick a date with a recorded pipeline run to see duration, segment counts, and carry/fail stats."
          />
        ) : (
          <>
            {dayOk ? (
              <FreshnessBanner latest={dayOk} />
            ) : (
              <div className="border border-hair px-4 py-3 font-mono text-xs text-warn">
                No successful run on {date} — see segment counts below.
              </div>
            )}
            {/* glassbox_economics: Baseline+. Freshness/status stay visible to Observer. */}
            <EntitledSurface artifactClass="glassbox_economics" tier={tier}>
              <PipelineKpiStrip kpis={kpis} />
            </EntitledSurface>
          </>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
