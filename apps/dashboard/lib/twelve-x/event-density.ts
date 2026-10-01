/**
 * Day-by-day macro load for the Events navigator: each calendar day in the
 * window gets an impact-weighted score (high 3, medium 2, low 1) so a day with
 * one central-bank decision reads heavier than a day of minor prints. Days with
 * no ingested events inside the window are kept at 0 so the strip stays a
 * continuous calendar rather than collapsing gaps.
 */
import { eventLocalDateKey } from './fetch';
import type { FxEconomicCalendarRow } from './types';

export interface DensityDay {
  date: string;
  count: number;
}

export interface EventDensity {
  days: DensityDay[];
  totalEvents: number;
  highCount: number;
  /** Day with the largest load, or null when the window is empty. */
  peak: DensityDay | null;
}

export function impactWeight(impact: string | null | undefined): number {
  const i = (impact ?? '').trim().toLowerCase();
  if (i === 'high') return 3;
  if (i === 'medium') return 2;
  return 1;
}

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

type DensityEvent = Pick<FxEconomicCalendarRow, 'event_date' | 'event_datetime_utc' | 'impact'>;

export function deriveEventDensity(events: DensityEvent[]): EventDensity {
  if (events.length === 0) return { days: [], totalEvents: 0, highCount: 0, peak: null };

  const load = new Map<string, number>();
  let highCount = 0;
  for (const e of events) {
    const key = eventLocalDateKey(e);
    load.set(key, (load.get(key) ?? 0) + impactWeight(e.impact));
    if (impactWeight(e.impact) === 3) highCount += 1;
  }

  const keys = [...load.keys()].sort();
  const days: DensityDay[] = [];
  for (let d = keys[0]; d <= keys[keys.length - 1]; d = addDays(d, 1)) {
    days.push({ date: d, count: load.get(d) ?? 0 });
  }
  const peak = days.reduce<DensityDay | null>(
    (best, d) => (d.count > 0 && (!best || d.count > best.count) ? d : best),
    null,
  );
  return { days, totalEvents: events.length, highCount, peak };
}

export function densitySummary(density: EventDensity): string {
  if (density.totalEvents === 0) return 'Macro load: no events ingested for this window.';
  const peak = density.peak ? ` Heaviest day ${density.peak.date}.` : '';
  return `Macro load across ${density.days.length} days: ${density.totalEvents} events, ${density.highCount} high impact.${peak}`;
}
