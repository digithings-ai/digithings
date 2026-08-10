'use client';

import { Clock, ExternalLink, X } from 'lucide-react';
import { Sheet, SheetContent, SheetTitle } from '@digithings/web';

import type { MatrixCell } from '@/lib/twelve-x/types';
import { directionStyle } from '@/lib/twelve-x/matrix-format';

/**
 * History content is separate from the Digiweb Sheet because portalled Sheet
 * content does not render in static-markup tests.
 */
export function MatrixCellHistoryPanelBody({
  cell,
  onClose,
  onOpenBrief,
}: {
  cell: MatrixCell;
  onClose: () => void;
  onOpenBrief: (sourceFile: string, runDate: string | null) => void;
}) {
  const totalViews = 1 + (cell.history?.length ?? 0);
  const allViews = [
    {
      run_date: cell.run_date,
      report_date: cell.report_date,
      source_file: cell.source_file,
      direction: cell.direction,
      conviction: cell.conviction,
      signal: cell.signal,
      rationale: cell.rationale,
      key_facts: cell.key_facts,
      targets: cell.targets,
      isPrimary: true,
    },
    ...(cell.history?.map((h) => ({ ...h, isPrimary: false })) ?? []),
  ];

  return (
    <>
      <div className="flex items-start gap-3 border-b border-hair px-5 py-4">
        <Clock size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-base font-semibold text-ink">
            {cell.broker} · {cell.currency}
          </h2>
          <div className="mt-1 text-[11px] text-ink-mute">
            <span className="tabular-nums">{totalViews} views</span> over recent window
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="-mr-1.5 -mt-1.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-ink-mute transition-colors hover:bg-ink/[0.06] hover:text-ink sm:h-9 sm:w-9"
        >
          <X size={18} aria-hidden />
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-5 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        {allViews.map((view) => {
          const style = directionStyle(view.direction);
          const asOf = view.report_date ?? view.run_date;
          return (
            <div
              key={`${view.source_file}-${view.run_date}`}
              className={`rounded-lg border ${style.border} bg-ink/[0.02] p-3 ${view.isPrimary ? 'ring-1 ring-accent/30' : ''}`}
            >
              <div className="flex items-center gap-2">
                <span className={`text-sm leading-none ${style.text}`} aria-hidden>
                  {style.glyph}
                </span>
                <span className={`text-xs font-medium ${style.text}`}>{view.direction}</span>
                {view.conviction ? (
                  <span className="text-[11px] uppercase text-ink-mute">· {view.conviction}</span>
                ) : null}
                {view.isPrimary ? (
                  <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-accent">
                    Latest
                  </span>
                ) : null}
                <span className="ml-auto font-mono text-[10px] tabular-nums text-ink-mute">
                  {asOf}
                </span>
              </div>

              {view.signal ? (
                <p className="mt-1.5 text-xs font-medium text-ink-soft">{view.signal}</p>
              ) : null}
              {view.rationale ? (
                <p className="mt-1 text-xs leading-snug text-ink-soft">{view.rationale}</p>
              ) : null}

              <button
                type="button"
                onClick={() => onOpenBrief(view.source_file, view.run_date)}
                className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-accent hover:underline"
              >
                Open brief <ExternalLink size={11} aria-hidden />
              </button>
            </div>
          );
        })}
      </div>
    </>
  );
}

/**
 * Digiweb Sheet showing a cell's primary view and older distinct views.
 */
export default function MatrixCellHistoryPanel({
  cell,
  onClose,
  onOpenBrief,
}: {
  cell: MatrixCell | null;
  onClose: () => void;
  onOpenBrief: (sourceFile: string, runDate: string | null) => void;
}) {
  if (!cell) return null;

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="flex w-full! max-w-md! flex-col gap-0 bg-term-bg p-0 shadow-2xl"
      >
        <SheetTitle className="sr-only">
          {cell.broker} {cell.currency} brief history
        </SheetTitle>
        <MatrixCellHistoryPanelBody
          cell={cell}
          onClose={onClose}
          onOpenBrief={(sourceFile, runDate) => {
            onClose();
            onOpenBrief(sourceFile, runDate);
          }}
        />
      </SheetContent>
    </Sheet>
  );
}
