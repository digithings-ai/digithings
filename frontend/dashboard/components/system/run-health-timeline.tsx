'use client';

import { SectionCard } from '@/components/observability/shared';
import { groupRunEpisodes, type RunEpisode, type RunOutcome } from '@/lib/run-episodes';
import type { AtlasRunDiagnostics } from '@/lib/types';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@digithings/web';

// Horizontal timeline — green for successful, orange for recovered/degraded, red for failed.
const SEGMENT_COLOR: Record<RunOutcome, string> = {
  ok: 'bg-accent',
  recovered: 'bg-warn/80',
  degraded: 'bg-warn/60',
  failed: 'bg-down',
};

function buildTooltipContent(ep: RunEpisode): string {
  const lines: string[] = [];

  // Run date, type, outcome
  lines.push(`${ep.runDate ?? '—'} · ${ep.runType ?? 'run'} · ${ep.outcome}`);

  // Attempts if > 1
  if (ep.attempts > 1) {
    lines.push(`${ep.attempts} attempts`);
  }

  // Latest raw status
  if (ep.latest.status) {
    lines.push(`Status: ${ep.latest.status}`);
  }

  // Segment counts
  const { segments_total, segments_ok, segments_carried, segments_failed } = ep.latest;
  if (segments_total != null && segments_ok != null) {
    lines.push(`Segments: ${segments_ok}/${segments_total}`);
    if (segments_carried != null && segments_carried > 0) {
      lines.push(`Carried: ${segments_carried}`);
    }
    if (segments_failed != null && segments_failed > 0) {
      lines.push(`Failed: ${segments_failed}`);
    }
  }

  // Duration
  if (ep.latest.duration_s != null) {
    lines.push(`Duration: ${ep.latest.duration_s.toFixed(1)}s`);
  }

  // Error summary
  if (ep.errorSummary) {
    lines.push(`Error: ${ep.errorSummary}`);
  }

  return lines.join(' · ');
}

function buildAriaLabel(ep: RunEpisode): string {
  const parts = [ep.runDate ?? 'Unknown date', ep.runType ?? 'run', ep.outcome];
  if (ep.attempts > 1) parts.push(`${ep.attempts} attempts`);
  if (ep.errorSummary) parts.push(`Error: ${ep.errorSummary}`);
  return parts.join(', ');
}

function TimelineBody({ episodes }: { episodes: ReturnType<typeof groupRunEpisodes> }) {
  // Reverse to show chronological order (oldest left, newest right)
  const chronological = [...episodes].reverse();
  const oldest = chronological[0]?.runDate ?? '—';
  const newest = chronological[chronological.length - 1]?.runDate ?? '—';

  return (
    <div className="space-y-3">
      <div className="flex h-3 gap-px overflow-hidden rounded">
        <TooltipProvider delay={200}>
          {chronological.map((ep) => (
            <Tooltip key={ep.key}>
              <TooltipTrigger
                render={
                  <button
                    type="button"
                    aria-label={buildAriaLabel(ep)}
                    className={`min-w-0 flex-1 transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${SEGMENT_COLOR[ep.outcome]}`}
                  />
                }
              />
              <TooltipContent side="bottom" className="max-w-xs font-mono text-xs">
                {buildTooltipContent(ep)}
              </TooltipContent>
            </Tooltip>
          ))}
        </TooltipProvider>
      </div>

      <div className="flex justify-between font-mono text-[10px] uppercase tracking-wide text-ink-mute tabular-nums">
        <span>{oldest}</span>
        <span>{newest}</span>
      </div>

      <div className="flex gap-4 font-mono text-[10px] uppercase tracking-wide text-ink-soft">
        <div className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-accent" aria-hidden />
          <span>Successful</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-warn/70" aria-hidden />
          <span>Recovered/Degraded</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-down" aria-hidden />
          <span>Failed</span>
        </div>
      </div>
    </div>
  );
}

export function RunHealthTimeline({
  diagnostics,
  compact = false,
}: {
  diagnostics: AtlasRunDiagnostics[];
  /** Bare timeline for Brief — skips SectionCard chrome. */
  compact?: boolean;
}) {
  const episodes = groupRunEpisodes(diagnostics);
  if (!episodes.length) return null;

  const body = <TimelineBody episodes={episodes} />;

  if (compact) {
    return (
      <div data-testid="brief-run-health-timeline" className="space-y-2">
        <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">Run health</p>
        {body}
      </div>
    );
  }

  return (
    <SectionCard
      title="Run health"
      subtitle="Compact horizontal timeline — green for successful, orange for recovered/degraded, red for failed."
    >
      {body}
    </SectionCard>
  );
}
