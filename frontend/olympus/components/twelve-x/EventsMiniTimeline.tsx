'use client';

import { CalendarClock } from 'lucide-react';
import type { FxEconomicCalendarRow } from '@/lib/twelve-x/types';
import { hasResolvedTime, eventInstant } from '@/lib/twelve-x/fetch';
import { useTwelveX } from './context';

function impactClass(impact: string): string {
  const i = impact.trim().toLowerCase();
  if (i === 'high') return 'bg-fin-red';
  if (i === 'medium') return 'bg-fin-amber';
  return 'bg-text-muted/60';
}

function localTime(e: FxEconomicCalendarRow): string {
  const inst = eventInstant(e);
  if (inst) return inst.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  return e.event_time ?? '—';
}

export default function EventsMiniTimeline({ events }: { events: FxEconomicCalendarRow[] }) {
  const { crossLink } = useTwelveX();
  return (
    <section className="glass-card flex flex-col gap-3 p-5">
      <header className="flex items-baseline gap-2">
        <CalendarClock size={15} className="shrink-0 text-fin-blue" aria-hidden />
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Today&rsquo;s events</h2>
        <button type="button" className="ml-auto text-[11px] text-fin-blue hover:underline" onClick={() => crossLink({ kind: 'tab', tab: 'events' })}>
          see more →
        </button>
      </header>
      {events.length === 0 ? (
        <p className="text-sm text-text-muted">No macro events scheduled today.</p>
      ) : (
        <ul className="grid gap-1.5">
          {events.map((e) => (
            <li key={e.id} className="flex items-center gap-2.5 text-xs">
              <span className="w-14 shrink-0 text-right font-mono tabular-nums text-text-secondary">{localTime(e)}</span>
              <span className={`h-2 w-2 shrink-0 rounded-full ${impactClass(e.impact)}`} aria-hidden />
              <span className="font-mono text-[10px] uppercase text-text-muted">{e.country}</span>
              <span className="truncate text-text-primary">{e.event_name}</span>
              {!hasResolvedTime(e) ? <span className="text-text-muted/60" title="venue-local time">≈</span> : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
