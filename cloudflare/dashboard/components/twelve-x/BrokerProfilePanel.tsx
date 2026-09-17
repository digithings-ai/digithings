'use client';

import { useMemo } from 'react';
import { Building2, ExternalLink, X } from 'lucide-react';
import { Sheet, SheetContent } from '@digithings/web';
import { Button } from '@digithings/web/ui';

import { MATRIX_COLUMNS } from '@/lib/twelve-x/types';
import type { MatrixCell } from '@/lib/twelve-x/types';
import { directionStyle, directionBucket, formatTargets } from '@/lib/twelve-x/matrix-format';
import { detailPanelSheetSizeClass } from '@/components/DetailPanelHeaderActions';

/**
 * Right-side slide-over profiling a SINGLE broker/desk — the "focus on one
 * broker, drill into what they're thinking" view. Opened by clicking a broker's
 * row label in the Matrix.
 *
 * Wave-2 (#4206): the hand-rolled scrim + right panel + window Escape listener
 * + body scroll-lock are now the shared @digithings/web Sheet (Base UI Dialog),
 * exactly like its sibling BriefPanel: same side/right geometry, Escape +
 * backdrop dismissal, focus trap, scroll lock, and the dashboard's black/50
 * scrim redress. `BrokerProfileBody` is the exported content half for the SSR
 * contract test (the popup lives in a portal that never renders under static
 * SSR). Fully derived from the MatrixCell set already in the Matrix (filtered
 * to this broker) — no extra fetch.
 */
export default function BrokerProfilePanel({
  broker,
  cells,
  onClose,
  onOpenBrief,
}: {
  broker: string | null;
  cells: MatrixCell[];
  onClose: () => void;
  onOpenBrief: (sourceFile: string, runDate: string | null) => void;
}) {
  if (!broker) return null;
  return (
    <Sheet open onOpenChange={(next) => (next ? undefined : onClose())}>
      {/* The `!` overrides fight the sheet's deliberately unlayered per-side
          geometry (75% / 24rem cap) and same-layer base dress — this panel
          keeps its shipped full-bleed-mobile / max-w-xl / term-bg look
          (MIGRATION.md cascade-layering contract). The scrim re-dress is
          app-wide in globals.css. */}
      <SheetContent
        side="right"
        showCloseButton={false}
        aria-label="Broker profile"
        className={`${detailPanelSheetSizeClass('default')} gap-0! bg-term-bg! shadow-2xl!`}
      >
        <BrokerProfileBody
          broker={broker}
          cells={cells}
          onClose={onClose}
          onOpenBrief={onOpenBrief}
        />
      </SheetContent>
    </Sheet>
  );
}

export function BrokerProfileBody({
  broker,
  cells,
  onClose,
  onOpenBrief,
}: {
  broker: string;
  cells: MatrixCell[];
  onClose?: () => void;
  onOpenBrief: (sourceFile: string, runDate: string | null) => void;
}) {
  // This broker's views, in canonical board-column order (extras after).
  const views = useMemo<MatrixCell[]>(() => {
    const mine = cells.filter((c) => c.broker === broker);
    const order = new Map(MATRIX_COLUMNS.map((c, i) => [c as string, i]));
    return [...mine].sort((a, b) => {
      const ai = order.get(a.column) ?? 99;
      const bi = order.get(b.column) ?? 99;
      if (ai !== bi) return ai - bi;
      return a.currency.localeCompare(b.currency);
    });
  }, [broker, cells]);

  // Net tilt tally across this desk's views.
  const tally = useMemo(() => {
    let bull = 0;
    let bear = 0;
    let watch = 0;
    for (const v of views) {
      const b = directionBucket(v.direction);
      if (b === 'bull') bull++;
      else if (b === 'bear') bear++;
      else if (b === 'watch') watch++;
    }
    return { bull, bear, watch };
  }, [views]);

  return (
    <>
      <div className="flex shrink-0 justify-center pt-2 sm:hidden" aria-hidden>
        <span className="h-1 w-9 bg-ink/20" />
      </div>
      <div className="flex items-start gap-3 border-b border-hair px-5 py-4">
        <Building2 size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-base font-semibold text-ink">{broker}</h2>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-mute">
            <span className="tabular-nums">
              {views.length} {views.length === 1 ? 'view' : 'views'}
            </span>
            {tally.bull > 0 ? (
              <span className="flex items-center gap-1 text-accent">
                <span aria-hidden>▲</span> {tally.bull} bull
              </span>
            ) : null}
            {tally.bear > 0 ? (
              <span className="flex items-center gap-1 text-warn">
                <span aria-hidden>▼</span> {tally.bear} bear
              </span>
            ) : null}
            {tally.watch > 0 ? (
              <span className="flex items-center gap-1 text-warn">
                <span aria-hidden>◆</span> {tally.watch} watch
              </span>
            ) : null}
          </div>
        </div>
        {onClose ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label="Close"
            className="-mr-1.5 -mt-1.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-none text-ink-mute transition-colors hover:bg-ink/[0.06] hover:text-ink sm:h-9 sm:w-9"
          >
            <X size={18} aria-hidden />
          </Button>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto px-5 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        {views.length === 0 ? (
          <p className="text-xs text-ink-mute">No standing views from this desk in the window.</p>
        ) : (
          views.map((v, i) => {
            const s = directionStyle(v.direction);
            const levels = formatTargets(v.targets);
            const asOf = v.report_date ?? v.run_date;
            return (
              <div
                key={`${v.column}-${v.currency}-${i}`}
                className={`rounded-none border ${s.border} bg-ink/[0.02] p-3`}
              >
                <div className="flex items-center gap-2">
                  <span className={`text-sm leading-none ${s.text}`} aria-hidden>
                    {s.glyph}
                  </span>
                  <span className="font-mono text-sm font-semibold text-ink">
                    {v.currency}
                  </span>
                  <span className={`text-xs font-medium ${s.text}`}>{v.direction}</span>
                  {v.conviction ? (
                    <span className="text-[11px] uppercase text-ink-mute">· {v.conviction}</span>
                  ) : null}
                  <span className="ml-auto min-w-0 shrink truncate font-mono text-[10px] tabular-nums text-ink-mute">
                    {asOf}
                  </span>
                </div>

                {v.signal ? (
                  <p className="mt-1.5 text-xs font-medium text-ink-soft">{v.signal}</p>
                ) : null}
                {v.rationale ? (
                  <p className="mt-1 text-xs leading-snug text-ink-soft">{v.rationale}</p>
                ) : null}
                {v.key_facts && v.key_facts.length > 0 ? (
                  <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-ink-mute">
                    {v.key_facts.map((f, n) => (
                      <li key={n}>{f}</li>
                    ))}
                  </ul>
                ) : null}
                {levels ? (
                  <p className="mt-1.5 text-[11px] text-ink-mute">
                    <span className="text-ink-soft">Levels:</span> {levels}
                  </p>
                ) : null}

                <Button
                  type="button"
                  variant="link"
                  size="xs"
                  onClick={() => onOpenBrief(v.source_file, v.run_date)}
                  className="mt-2 inline-flex h-auto items-center gap-1 p-0 text-[11px] font-medium text-accent"
                >
                  Open brief <ExternalLink size={11} aria-hidden />
                </Button>
              </div>
            );
          })
        )}
      </div>
    </>
  );
}
