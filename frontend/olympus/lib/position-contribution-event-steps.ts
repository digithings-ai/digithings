import type { PositionContributionPoint } from '@/lib/position-contribution-series';
import type { PositionPriceChartEvent } from '@/lib/types';

function rowOnOrAfter(rows: PositionContributionPoint[], iso: string): PositionContributionPoint | null {
  const exact = rows.find((r) => r.date === iso);
  if (exact) return exact;
  return rows.find((r) => r.date >= iso) ?? null;
}

export type EventContributionStep = {
  id: string;
  kind: 'event' | 'tail';
  event: PositionPriceChartEvent['event'] | null;
  date: string;
  label: string;
  /** Change in cumulative ppt since the previous step anchor. */
  deltaPp: number;
  /** Cumulative ppt at this step’s NAV anchor. */
  runCumPp: number;
};

/**
 * Splits NAV-based cumulative contribution into steps between portfolio activity dates.
 * Each step’s delta is (cumPp at event) − (cumPp at previous anchor); tail covers last event → window end.
 */
export function buildEventContributionSteps(
  chartRows: PositionContributionPoint[],
  events: PositionPriceChartEvent[]
): EventContributionStep[] {
  if (!chartRows.length) return [];
  const first = chartRows[0];
  const last = chartRows[chartRows.length - 1];
  const evs = [...events]
    .filter((e) => e.event !== 'HOLD')
    .filter((e) => e.date >= first.date && e.date <= last.date)
    .sort((a, b) => a.date.localeCompare(b.date) || String(a.event).localeCompare(String(b.event)));

  let prevCum = first.cumPp;
  const out: EventContributionStep[] = [];
  let seq = 0;

  for (const ev of evs) {
    const row = rowOnOrAfter(chartRows, ev.date);
    if (!row) continue;
    const runCum = row.cumPp;
    const deltaPp = runCum - prevCum;
    out.push({
      id: `ev-${seq++}`,
      kind: 'event',
      event: ev.event,
      date: row.date,
      label: `${ev.event} · ${row.date}`,
      deltaPp,
      runCumPp: runCum,
    });
    prevCum = runCum;
  }

  const tailDelta = last.cumPp - prevCum;
  if (Math.abs(tailDelta) > 1e-9 || !out.length) {
    out.push({
      id: 'tail',
      kind: 'tail',
      event: null,
      date: last.date,
      label: out.length ? `After last activity → ${last.date}` : `Window ${first.date} → ${last.date}`,
      deltaPp: out.length ? tailDelta : last.cumPp - first.cumPp,
      runCumPp: last.cumPp,
    });
  }

  return out;
}
