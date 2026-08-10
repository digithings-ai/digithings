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

export function RunHealthTimeline({ diagnostics }: { diagnostics: AtlasRunDiagnostics[] }) {
  const episodes = groupRunEpisodes(diagnostics);
  if (!episodes.length) return null;

  // Reverse to show chronological order (oldest left, newest right)
  const chronological = [...episodes].reverse();
  const oldest = chronological[0]?.runDate ?? '—';
  const newest = chronological[chronological.length - 1]?.runDate ?? '—';

  return (
    <SectionCard
      title="Run health"
      subtitle="Compact horizontal timeline — green for successful, orange for recovered/degraded, red for failed."
    >
      <div className="space-y-3">
        {/* Timeline bar */}
        <div className="flex gap-px h-3 overflow-hidden rounded">
          <TooltipProvider delay={200}>
            {chronological.map((ep) => (
              <Tooltip key={ep.key}>
                <TooltipTrigger
                  render={
                    <button
                      type="button"
                      aria-label={buildAriaLabel(ep)}
                      className={`flex-1 min-w-0 transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${SEGMENT_COLOR[ep.outcome]}`}
                    />
                  }
                />
                <TooltipContent side="bottom" className="font-mono text-xs max-w-xs">
                  {buildTooltipContent(ep)}
                </TooltipContent>
              </Tooltip>
            ))}
          </TooltipProvider>
        </div>

        {/* Date endpoints */}
        <div className="flex justify-between text-[10px] font-mono tabular-nums text-ink-mute uppercase tracking-wide">
          <span>{oldest}</span>
          <span>{newest}</span>
        </div>

        {/* Legend */}
        <div className="flex gap-4 text-[10px] font-mono uppercase tracking-wide text-ink-soft">
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full bg-accent" aria-hidden />
            <span>Successful</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full bg-warn/70" aria-hidden />
            <span>Recovered/Degraded</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full bg-down" aria-hidden />
            <span>Failed</span>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}
