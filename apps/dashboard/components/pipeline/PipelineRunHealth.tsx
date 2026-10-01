'use client';

import { useMemo } from 'react';
import { ChevronDown } from 'lucide-react';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Badge,
  EmptyState,
  Skeleton,
  SkeletonGroup,
} from '@digithings/ui/ui';
import { latestSuccessfulRun } from '@/components/system/freshness-banner';
import { AsOfBadge } from '@/components/shared/as-of-badge';
import { EntitledSurface } from '@/components/entitled-surface';
import { buildDayKpis } from '@/lib/pipeline-kpis';
import { groupRunEpisodes } from '@/lib/run-episodes';
import type { PipelineScope } from '@/lib/pipelines';
import type { ResearchRunDiagnostics } from '@/lib/types';
import type { PlanTier } from '@/lib/entitlements';
import { runStatusView } from '@/lib/run-status';
import PipelineKpiStrip, { PipelineKpiDetail } from './PipelineKpiStrip';
import { useRunDiagnostics, type RunDiagnosticsState } from './use-run-diagnostics';

function forDate(diagnostics: ResearchRunDiagnostics[], date: string): ResearchRunDiagnostics[] {
  return diagnostics.filter((d) => d.run_date === date);
}

/**
 * Run-health band for the selected date. The collapsed state IS the band: one compact inline row
 * (status, KPI chips + duration sparkline, freshness) so the graph keeps the height. Phase bars and
 * the segment composition sit behind the collapse, closed by default.
 */
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
  const view = runStatusView(kpis.kind, kpis.status);
  const hasRuns = dayRuns.length > 0;

  return (
    <Collapsible data-testid="pipeline-run-health" defaultOpen={false} className="group border-b border-hair bg-surface">
      <div className="flex min-h-10 flex-wrap items-center gap-x-3 gap-y-1 px-3 py-1 md:px-4">
        <CollapsibleTrigger
          aria-label="Toggle run health detail"
          className="flex shrink-0 items-center gap-2 py-1 text-left transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
        >
          <ChevronDown
            size={14}
            className="shrink-0 -rotate-90 text-ink-mute transition-transform group-data-open:rotate-0"
            aria-hidden
          />
          <span className="font-mono text-[0.62rem] font-semibold uppercase tracking-[0.1em] text-ink-mute">
            Run health
          </span>
          <span className="font-mono text-xs tabular-nums text-ink-soft">
            {date}
            {loading ? ' · Loading…' : unavailable ? ' · Run data unavailable' : !kpis.hasTelemetry ? ' · No run telemetry' : null}
          </span>
        </CollapsibleTrigger>

        {!loading && !unavailable && kpis.hasTelemetry && (
          <Badge
            variant={view.tone === 'warn' ? 'warn' : view.tone === 'accent' ? 'accent' : 'neutral'}
            title={view.meaning}
            data-testid="pipeline-run-status"
            data-status-kind={view.kind}
          >
            {view.label}
          </Badge>
        )}

        {!loading && !unavailable && hasRuns && (
          // glassbox_economics: Baseline+. Status/freshness stay visible to Observer.
          <EntitledSurface artifactClass="glassbox_economics" tier={tier}>
            <PipelineKpiStrip kpis={kpis} />
          </EntitledSurface>
        )}

        {!loading && !unavailable && hasRuns && (
          <span data-testid="pipeline-freshness" className="ml-auto flex items-center gap-2 font-mono text-[0.65rem] text-ink-mute">
            {dayOk ? (
              <>
                <span>
                  Last successful run <span className="tabular-nums text-ink-soft">{dayOk.run_date ?? '—'}</span>
                  {dayOk.run_type ? ` · ${dayOk.run_type}` : ''}
                </span>
                <AsOfBadge date={dayOk.run_date} createdAt={dayOk.created_at} />
              </>
            ) : (
              <span className="text-warn">No successful run on {date}</span>
            )}
          </span>
        )}
      </div>

      <CollapsibleContent className="space-y-3 border-t border-hair px-3 py-3 md:px-4">
        {loading ? (
          <SkeletonGroup aria-label="Loading run diagnostics" className="flex flex-col gap-3">
            <Skeleton variant="block" className="h-6 w-full" />
          </SkeletonGroup>
        ) : unavailable ? (
          <EmptyState
            dress="glass"
            variant="error"
            title="Run data unavailable"
            body="Run telemetry could not be read, so run health is not shown. This is not the same as a date with no run."
          />
        ) : !hasRuns ? (
          <EmptyState
            dress="glass"
            data-reveal
            title="No run for this date"
            body="Pick a date with a recorded pipeline run to see duration, segment counts, and carry/fail stats."
          />
        ) : (
          <EntitledSurface artifactClass="glassbox_economics" tier={tier}>
            <PipelineKpiDetail kpis={kpis} />
          </EntitledSurface>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
