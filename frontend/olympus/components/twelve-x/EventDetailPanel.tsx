'use client';

import { useCallback, useEffect } from 'react';
import { CalendarClock, Globe, Users, X } from 'lucide-react';

import type { FxEconomicCalendarRow } from '@/lib/twelve-x/types';
import type { MatchedOpinions } from './EventsTab';

/** Impact → trader-facing RISK level + .fin-* color. */
function riskLevel(impact: string): { label: string; text: string; dot: string } {
  const i = (impact ?? '').trim().toLowerCase();
  if (i === 'high') return { label: 'High risk', text: 'text-fin-red', dot: 'bg-fin-red' };
  if (i === 'medium' || i === 'med')
    return { label: 'Medium risk', text: 'text-fin-amber', dot: 'bg-fin-amber' };
  return { label: 'Low risk', text: 'text-text-muted', dot: 'bg-text-muted/60' };
}

/** Format an ISO timestamptz to the viewer's locale time, or null when absent. */
function formatLocalTime(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

function hasValue(v: string | null | undefined): v is string {
  return v != null && v !== '';
}

/**
 * Right-side slide-over for a single calendar event, opened from both the Events
 * list and the timeline. Mirrors BriefPanel's slide-over (scrim + right panel,
 * Esc-to-close, body scroll-lock). Prop-driven: the parent owns the open state
 * (`event != null` ⇒ open) and passes the already-matched broker opinions so this
 * panel renders the same desk-commentary shape the list/timeline derive.
 */
export default function EventDetailPanel({
  event,
  opinions,
  onClose,
}: {
  event: FxEconomicCalendarRow | null;
  opinions: MatchedOpinions | null;
  onClose: () => void;
}) {
  const open = event != null;
  const handleClose = useCallback(() => onClose(), [onClose]);

  // Close on Escape while open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, handleClose]);

  // Lock body scroll while the panel is open (mirrors BriefPanel / the nav drawer).
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!event) return null;

  const risk = riskLevel(event.impact);
  const time = formatLocalTime(event.event_datetime_utc) ?? event.event_time ?? null;
  const hasOpinions = Boolean(opinions && opinions.mentions > 0);

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Event detail">
      {/* Scrim */}
      <button
        type="button"
        aria-label="Close event detail"
        onClick={handleClose}
        className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
      />

      {/* Panel */}
      <div className="absolute inset-y-0 right-0 flex w-full max-w-xl flex-col border-l border-border-subtle bg-bg-secondary shadow-2xl">
        {/* Grab bar — phone-only affordance hinting the sheet is dismissable. */}
        <div className="flex shrink-0 justify-center pt-2 sm:hidden" aria-hidden>
          <span className="h-1 w-9 rounded-full bg-white/20" />
        </div>
        <div className="flex items-start gap-3 border-b border-border-subtle px-5 py-4">
          <CalendarClock size={18} className="mt-0.5 shrink-0 text-fin-blue" aria-hidden />
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold leading-snug text-text-primary">
              {event.event_name}
            </h2>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
              <span className="flex items-center gap-1 font-mono uppercase text-text-muted">
                <Globe size={11} aria-hidden />
                {event.country}
              </span>
              <span className={`flex items-center gap-1.5 font-medium ${risk.text}`}>
                <span className={`h-2 w-2 rounded-full ${risk.dot}`} aria-hidden />
                {risk.label}
              </span>
              {time ? (
                <span className="font-mono tabular-nums text-text-secondary">{time}</span>
              ) : null}
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            aria-label="Close"
            className="-mr-1.5 -mt-1.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-white/[0.06] hover:text-text-primary sm:h-9 sm:w-9"
          >
            <X size={18} aria-hidden />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          {/* Prior · Forecast · Actual */}
          <div className="grid grid-cols-3 gap-2">
            {(
              [
                ['Prior', event.prior, 'text-text-secondary'],
                ['Forecast', event.forecast, 'text-text-secondary'],
                ['Actual', event.actual, 'text-text-primary'],
              ] as const
            ).map(([label, value, valueClass]) => (
              <div
                key={label}
                className="rounded-lg border border-border-subtle bg-white/[0.02] px-3 py-2"
              >
                <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                  {label}
                </div>
                <div className={`mt-0.5 font-mono text-sm tabular-nums ${valueClass}`}>
                  {hasValue(value) ? value : '—'}
                </div>
              </div>
            ))}
          </div>

          {/* What desks said */}
          <div>
            <h3 className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              <Users size={12} aria-hidden />
              What desks said
              {hasOpinions ? (
                <span className="tabular-nums text-text-secondary">
                  · {opinions!.mentions} mention{opinions!.mentions === 1 ? '' : 's'}
                </span>
              ) : null}
            </h3>

            {hasOpinions ? (
              <div className="space-y-2">
                {opinions!.brokers.length > 0 ? (
                  <p className="text-xs text-text-muted">
                    Cited by{' '}
                    <span className="text-text-secondary">{opinions!.brokers.join(', ')}</span>.
                  </p>
                ) : null}
                {opinions!.citations.length > 0 ? (
                  opinions!.citations.map((c, i) => (
                    <div
                      key={`${c.broker}-${c.source_file}-${i}`}
                      className="rounded-lg bg-white/[0.02] p-3"
                    >
                      <div className="mb-1 font-mono text-xs font-semibold text-text-primary">
                        {c.broker || 'Unknown desk'}
                      </div>
                      {c.expected_outcome ? (
                        <p className="text-xs leading-snug text-text-secondary">
                          <span className="text-text-muted">Expected: </span>
                          {c.expected_outcome}
                        </p>
                      ) : null}
                      {c.fx_impact ? (
                        <p className="mt-1 text-xs leading-snug text-text-secondary">
                          <span className="text-text-muted">FX impact: </span>
                          {c.fx_impact}
                        </p>
                      ) : null}
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-text-muted">No broker detail available.</p>
                )}
              </div>
            ) : (
              <p className="text-xs text-text-muted">No desk commentary for this event yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
