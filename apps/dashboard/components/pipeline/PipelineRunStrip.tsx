'use client';

import { StatusDot, StatusStrip, Skeleton } from '@digithings/ui/ui';
import { summariseRunStrip, type RunStripCell } from '@/lib/pipeline-run-strip';
import { runStatusView } from '@/lib/run-status';

const LEGEND = [
  { tone: 'ok', text: 'complete (carry is normal)', title: `${runStatusView('complete').meaning} ${runStatusView('complete-with-carry').meaning}` },
  { tone: 'warn', text: 'retried or failed', title: `${runStatusView('attention').meaning} ${runStatusView('failed').meaning}` },
  { tone: 'off', text: 'no telemetry', title: runStatusView('no-telemetry').meaning },
  { tone: 'idle', text: 'no run', title: runStatusView('no-run').meaning },
] as const;

export interface PipelineRunStripProps {
  cells: RunStripCell[];
  selectedDate: string;
  onSelect: (date: string) => void;
  loading?: boolean;
}

/**
 * 30-day run strip: one cell per calendar day, toned by outcome. Doubles as the
 * date selector (a run day is clickable; a no-run day is inert). Health tones
 * only, from the shared run-status vocabulary (same reading as the Brief): accent = complete
 * (carry alone is normal for delta runs), warn = retried/degraded/failed, mute = no telemetry,
 * hollow = no run. The legend spells this out.
 */
export default function PipelineRunStrip({ cells, selectedDate, onSelect, loading = false }: PipelineRunStripProps) {
  const n = cells.length || 1;
  const selectedIdx = cells.findIndex((c) => c.date === selectedDate);
  const { runs, healthy, attention, carried } = summariseRunStrip(cells);

  if (loading) {
    return (
      <div data-testid="pipeline-run-strip" aria-busy="true" className="border-b border-hair bg-surface px-3 py-2 md:px-4">
        <Skeleton variant="block" className="h-[18px] w-full" />
      </div>
    );
  }

  return (
    <div data-testid="pipeline-run-strip" className="border-b border-hair bg-surface px-3 py-2 md:px-4">
      <div className="flex items-center gap-3">
        <span className="shrink-0 font-mono text-[0.62rem] font-semibold uppercase tracking-[0.1em] text-ink-mute">
          {n}d runs
        </span>
        <div className="min-w-0 flex-1">
          {/*
            The kit StatusStrip has no per-cell disabled state (onSelect turns EVERY cell into a
            focusable button). So the strip renders inert, and an aligned overlay adds a button
            only over run days; no-run cells get a non-focusable spacer. Kit follow-up: a
            per-cell `disabled`/`interactive` flag on StatusCell would remove this overlay.
          */}
          <div className="relative">
            <StatusStrip
              height={18}
              label={`Run outcome, last ${n} days: ${healthy} complete, ${carried} complete with carry, ${attention} need attention, ${runs} run days`}
              cells={cells.map((c) => ({ key: c.key, tone: c.tone, label: c.label }))}
            />
            <div className="absolute inset-px flex gap-px" data-testid="pipeline-run-strip-actions">
              {cells.map((c) =>
                c.outcome !== null ? (
                  <button
                    key={c.key}
                    type="button"
                    data-testid="pipeline-run-strip-select"
                    title={c.label}
                    aria-label={`Open ${c.label}`}
                    aria-current={c.date === selectedDate ? 'date' : undefined}
                    onClick={() => onSelect(c.date)}
                    className="block h-full min-w-0 flex-1 basis-0 bg-transparent hover:bg-ink/10 focus-visible:outline focus-visible:outline-1 focus-visible:outline-accent"
                  />
                ) : (
                  <span key={c.key} aria-hidden className="block h-full min-w-0 flex-1 basis-0" />
                ),
              )}
            </div>
          </div>
          <div className="relative h-1" aria-hidden>
            {selectedIdx >= 0 && (
              <span
                data-testid="pipeline-run-strip-marker"
                className="absolute top-0 block h-0.5 bg-ink"
                style={{ left: `${(selectedIdx / n) * 100}%`, width: `${100 / n}%` }}
              />
            )}
          </div>
        </div>
      </div>
      <div className="mt-0.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 font-mono text-[0.6rem] text-ink-mute">
        <span className="tabular-nums" aria-hidden>{cells[0]?.date}</span>
        <ul data-testid="pipeline-run-strip-legend" className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[0.62rem]">
          {LEGEND.map((item) => (
            <li key={item.text} title={item.title} className="flex items-center gap-1">
              <StatusDot tone={item.tone} size="sm" />
              {item.text}
            </li>
          ))}
        </ul>
        <span className="tabular-nums" aria-hidden>{cells[cells.length - 1]?.date}</span>
      </div>
    </div>
  );
}
