'use client';

import Link from 'next/link';
import { useState } from 'react';
import { ChevronLeft, ChevronRight, GitBranch } from 'lucide-react';
import type { AtlasRunDiagnostics } from '@/lib/types';
import { groupRunEpisodes, type RunEpisode, type RunOutcome } from '@/lib/run-episodes';
import {
  buildWeekDaySlots,
  formatWeekRangeLabel,
  mondayOfWeek,
  shiftWeekStart,
} from '@/lib/run-health-week';
import { formatDuration } from '@/components/system/run-economics-row';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@digithings/web';

export interface BriefRunHealth {
  status: string | null;
  runDate: string | null;
  finishedAt: string | null;
  segmentsOk: number | null;
  segmentsTotal: number | null;
  segmentsCarried: number | null;
  segmentsFailed: number | null;
  durationS: number | null;
}

type Tone = 'neutral' | 'positive' | 'negative' | 'warning';

const SEGMENT_COLOR: Record<RunOutcome, string> = {
  ok: 'bg-accent',
  recovered: 'bg-warn/80',
  degraded: 'bg-warn/60',
  failed: 'bg-down',
};

function toneClass(tone: Tone): string {
  if (tone === 'positive') return 'text-up';
  if (tone === 'negative') return 'text-down';
  if (tone === 'warning') return 'text-warn';
  return 'text-ink';
}

function runStatus(runHealth: BriefRunHealth | null | undefined): {
  label: string;
  detail: string;
  tone: Tone;
} {
  if (runHealth === undefined) {
    return {
      label: 'Checking pipeline status',
      detail: 'Reading public run telemetry',
      tone: 'neutral',
    };
  }
  if (!runHealth) {
    return {
      label: 'Pipeline status unavailable',
      detail: 'No public run telemetry',
      tone: 'neutral',
    };
  }

  const status = (runHealth.status || '').toLowerCase();
  const failed = runHealth.segmentsFailed ?? 0;
  const carried = runHealth.segmentsCarried ?? 0;
  const segmentDetail =
    runHealth.segmentsOk != null && runHealth.segmentsTotal != null
      ? `${runHealth.segmentsOk} / ${runHealth.segmentsTotal} segments`
      : 'Segment coverage unavailable';

  if (failed > 0 || ['failed', 'error'].includes(status)) {
    return { label: 'Pipeline needs attention', detail: segmentDetail, tone: 'negative' };
  }
  if (carried > 0 || ['partial', 'degraded'].includes(status)) {
    return { label: 'Pipeline completed with carry', detail: segmentDetail, tone: 'warning' };
  }
  if (['completed', 'complete', 'success', 'succeeded', 'ok'].includes(status)) {
    return { label: 'Pipeline complete', detail: segmentDetail, tone: 'positive' };
  }
  return {
    label: status ? `Pipeline ${status}` : 'Pipeline status unavailable',
    detail: segmentDetail,
    tone: 'neutral',
  };
}

function buildTooltipContent(ep: RunEpisode): string {
  const lines: string[] = [];
  lines.push(`${ep.runDate ?? '—'} · ${ep.runType ?? 'run'} · ${ep.outcome}`);
  if (ep.attempts > 1) lines.push(`${ep.attempts} attempts`);
  if (ep.latest.status) lines.push(`Status: ${ep.latest.status}`);
  const { segments_total, segments_ok, segments_carried, segments_failed } = ep.latest;
  if (segments_total != null && segments_ok != null) {
    lines.push(`Segments: ${segments_ok}/${segments_total}`);
    if (segments_carried != null && segments_carried > 0) lines.push(`Carried: ${segments_carried}`);
    if (segments_failed != null && segments_failed > 0) lines.push(`Failed: ${segments_failed}`);
  }
  if (ep.latest.duration_s != null) lines.push(`Duration: ${ep.latest.duration_s.toFixed(1)}s`);
  if (ep.errorSummary) lines.push(`Error: ${ep.errorSummary}`);
  return lines.join(' · ');
}

function buildAriaLabel(ep: RunEpisode): string {
  const parts = [ep.runDate ?? 'Unknown date', ep.runType ?? 'run', ep.outcome];
  if (ep.attempts > 1) parts.push(`${ep.attempts} attempts`);
  if (ep.errorSummary) parts.push(`Error: ${ep.errorSummary}`);
  return parts.join(', ');
}

/** Compact summary tiles — only emit optional ops stats when the row actually has them. */
export function buildLatestRunCards(
  runHealth: BriefRunHealth,
  latestDiag: AtlasRunDiagnostics | null
): Array<{ label: string; value: string }> {
  const cards: Array<{ label: string; value: string }> = [
    {
      label: 'Duration',
      value: runHealth.durationS != null ? formatDuration(runHealth.durationS) : '—',
    },
    {
      label: 'Segments',
      value:
        runHealth.segmentsOk != null && runHealth.segmentsTotal != null
          ? `${runHealth.segmentsOk}/${runHealth.segmentsTotal}`
          : '—',
    },
    {
      label: 'Carry',
      value: runHealth.segmentsCarried != null ? String(runHealth.segmentsCarried) : '—',
    },
    {
      label: 'Fail',
      value: runHealth.segmentsFailed != null ? String(runHealth.segmentsFailed) : '—',
    },
  ];

  if (!latestDiag) return cards;

  if (latestDiag.model) cards.push({ label: 'Model', value: latestDiag.model });
  if (latestDiag.llm_calls != null) cards.push({ label: 'Calls', value: String(latestDiag.llm_calls) });
  if (latestDiag.total_tokens != null) {
    cards.push({ label: 'Tokens', value: latestDiag.total_tokens.toLocaleString('en-US') });
  }
  if (latestDiag.error_summary) cards.push({ label: 'Error', value: latestDiag.error_summary });
  if (latestDiag.search_calls != null) {
    cards.push({ label: 'Search', value: String(latestDiag.search_calls) });
  }

  return cards;
}

function WeekBar({
  diagnostics,
  weekStart,
  onPrev,
  onNext,
}: {
  diagnostics: AtlasRunDiagnostics[];
  weekStart: string;
  onPrev: () => void;
  onNext: () => void;
}) {
  const episodes = groupRunEpisodes(diagnostics);
  const slots = buildWeekDaySlots(episodes, weekStart);
  const rangeLabel = formatWeekRangeLabel(weekStart);

  return (
    <div data-testid="brief-run-health-week" className="mt-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          aria-label="Previous week"
          onClick={onPrev}
          className="inline-flex h-6 w-6 items-center justify-center text-ink-mute transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
        >
          <ChevronLeft size={14} aria-hidden />
        </button>
        <p className="font-mono text-[10px] uppercase tracking-wide text-ink-mute tabular-nums">
          {rangeLabel}
        </p>
        <button
          type="button"
          aria-label="Next week"
          onClick={onNext}
          className="inline-flex h-6 w-6 items-center justify-center text-ink-mute transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/50"
        >
          <ChevronRight size={14} aria-hidden />
        </button>
      </div>

      <TooltipProvider delay={200}>
        <div className="grid grid-cols-7 gap-1">
          {slots.map((slot) => {
            if (!slot.episode) {
              return (
                <div key={slot.date} className="min-w-0 space-y-1">
                  <div
                    data-testid={`week-day-empty-${slot.date}`}
                    aria-label={`${slot.date}, no run`}
                    className="h-2.5 rounded-sm border border-dashed border-hair bg-transparent"
                  />
                  <p className="text-center font-mono text-[9px] uppercase tracking-wide text-ink-mute">
                    {slot.weekday}
                  </p>
                </div>
              );
            }

            const ep = slot.episode;
            return (
              <div key={slot.date} className="min-w-0 space-y-1">
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <button
                        type="button"
                        data-testid={`week-day-${slot.date}`}
                        aria-label={buildAriaLabel(ep)}
                        className={`h-2.5 w-full rounded-sm transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/60 ${SEGMENT_COLOR[ep.outcome]}`}
                      />
                    }
                  />
                  <TooltipContent side="bottom" className="max-w-xs font-mono text-xs">
                    {buildTooltipContent(ep)}
                  </TooltipContent>
                </Tooltip>
                <p className="text-center font-mono text-[9px] uppercase tracking-wide text-ink-mute">
                  {slot.weekday}
                </p>
              </div>
            );
          })}
        </div>
      </TooltipProvider>
    </div>
  );
}

export function BriefPipelineHealth({
  runHealth,
  diagnostics,
  /** Injectable clock for tests — defaults to today (UTC calendar date). */
  now = new Date(),
  /** Controlled week start (Monday YYYY-MM-DD); defaults to current week. */
  initialWeekStart,
}: {
  runHealth: BriefRunHealth | null | undefined;
  diagnostics: AtlasRunDiagnostics[];
  now?: Date;
  initialWeekStart?: string;
}) {
  const pipeline = runStatus(runHealth);
  const [weekStart, setWeekStart] = useState(
    () => initialWeekStart ?? mondayOfWeek(now)
  );

  const latestDiag =
    runHealth?.runDate != null
      ? diagnostics.find((d) => d.run_date === runHealth.runDate) ?? null
      : diagnostics[0] ?? null;

  const cards =
    runHealth != null ? buildLatestRunCards(runHealth, latestDiag) : null;

  const historyMissing = diagnostics.length === 0 && runHealth !== undefined;

  return (
    <div data-testid="brief-pipeline-health" className="px-5 py-4 sm:px-6">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[10px] font-bold uppercase tracking-widest text-ink-mute">
          Pipeline health
        </p>
        <Link
          href="/pipeline"
          className="inline-flex items-center gap-1 text-[10px] font-medium text-accent hover:underline"
          aria-label="Open pipeline"
        >
          <GitBranch size={12} className={toneClass(pipeline.tone)} aria-hidden />
          Open
        </Link>
      </div>

      <p className={`mt-1 text-sm font-semibold ${toneClass(pipeline.tone)}`}>{pipeline.label}</p>
      <p className="mt-0.5 font-mono text-[10px] tabular-nums text-ink-mute">{pipeline.detail}</p>

      {cards ? (
        <div
          data-testid="brief-pipeline-summary"
          className="mt-3 grid grid-cols-2 gap-px overflow-hidden border border-hair bg-hair"
        >
          {cards.map((card) => (
            <div key={card.label} className="min-w-0 bg-surface px-2.5 py-2">
              <span className="block font-mono text-[9px] uppercase tracking-wider text-ink-mute">
                {card.label}
              </span>
              <span className="mt-0.5 block truncate font-mono text-xs tabular-nums text-ink">
                {card.value}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {historyMissing ? (
        <p className="mt-3 text-[11px] leading-snug text-ink-mute">
          Run history unavailable — no public telemetry rows returned.
        </p>
      ) : (
        <WeekBar
          diagnostics={diagnostics}
          weekStart={weekStart}
          onPrev={() => setWeekStart((w) => shiftWeekStart(w, -1))}
          onNext={() => setWeekStart((w) => shiftWeekStart(w, 1))}
        />
      )}
    </div>
  );
}
