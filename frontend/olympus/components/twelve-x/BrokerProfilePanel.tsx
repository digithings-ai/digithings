'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Building2, ExternalLink, X } from 'lucide-react';

import { MATRIX_COLUMNS } from '@/lib/twelve-x/types';
import type { MatrixCell } from '@/lib/twelve-x/types';
import { directionStyle, directionBucket, formatTargets } from '@/lib/twelve-x/matrix-format';

/**
 * Right-side slide-over profiling a SINGLE broker/desk — the "focus on one
 * broker, drill into what they're thinking" view. Opened by clicking a broker's
 * row label in the Matrix. Mirrors EventDetailPanel/BriefPanel (scrim + right
 * panel, Esc-to-close, body scroll-lock, reduced-motion-aware entrance slide).
 * Fully derived from the MatrixCell set already in the Matrix (filtered to
 * this broker) — no extra fetch.
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
  const open = broker != null;
  const handleClose = useCallback(() => onClose(), [onClose]);

  // Mount flag driving the entrance slide (mirrors BriefPanel's Sheet, whose
  // entrance is a reduced-motion-aware translate; this hand-rolled overlay has
  // no Base UI transition primitive, so we fake the same one-motion-moment by
  // flipping this a frame after open so the transition has a starting state.
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setEntered(open));
    return () => cancelAnimationFrame(id);
  }, [open]);

  // Close on Escape while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, handleClose]);

  // Lock body scroll while open (mirrors EventDetailPanel / BriefPanel).
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // This broker's views, in canonical board-column order (extras after).
  const views = useMemo<MatrixCell[]>(() => {
    if (!broker) return [];
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

  if (!broker) return null;

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Broker profile">
      {/* Scrim */}
      <button
        type="button"
        aria-label="Close broker profile"
        onClick={handleClose}
        className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
      />

      {/* Panel */}
      <div
        className={`absolute inset-y-0 right-0 flex w-full max-w-xl flex-col border-l border-hair bg-term-bg shadow-2xl transition-transform duration-200 ease-in-out motion-reduce:transition-none motion-reduce:translate-x-0 ${entered ? 'translate-x-0' : 'translate-x-10'}`}
      >
        <div className="flex shrink-0 justify-center pt-2 sm:hidden" aria-hidden>
          <span className="h-1 w-9 rounded-full bg-ink/20" />
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
          <button
            type="button"
            onClick={handleClose}
            aria-label="Close"
            className="-mr-1.5 -mt-1.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-ink-mute transition-colors hover:bg-ink/[0.06] hover:text-ink sm:h-9 sm:w-9"
          >
            <X size={18} aria-hidden />
          </button>
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
                  className={`rounded-lg border ${s.border} bg-ink/[0.02] p-3`}
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
                    <span className="ml-auto font-mono text-[10px] tabular-nums text-ink-mute">
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

                  <button
                    type="button"
                    onClick={() => onOpenBrief(v.source_file, v.run_date)}
                    className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-accent hover:underline"
                  >
                    Open brief <ExternalLink size={11} aria-hidden />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
