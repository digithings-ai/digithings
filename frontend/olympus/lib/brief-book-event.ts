import type { DashboardPositionEvent } from './types';

/**
 * Brief "Last recorded book event" — only material ledger moves, never
 * execute_at_open derived fallbacks with engineering jargon or +0.0pp noise.
 */

/** Weight move in percentage points, or null when unknown. */
export function eventWeightDeltaPp(event: DashboardPositionEvent): number | null {
  if (event.weight_change_pct != null && Number.isFinite(event.weight_change_pct)) {
    return event.weight_change_pct;
  }
  if (event.weight_pct != null && event.prev_weight_pct != null) {
    return event.weight_pct - event.prev_weight_pct;
  }
  return null;
}

/**
 * True when the delta rounds to a non-zero 1-decimal pp move (desk display).
 * OPEN/EXIT without measurable weights still count as ledger events.
 */
export function isMaterialBookEvent(event: DashboardPositionEvent): boolean {
  const kind = (event.event || '').trim().toUpperCase();
  if (!kind || kind === 'HOLD') return false;

  const delta = eventWeightDeltaPp(event);
  if (delta == null) {
    return kind === 'OPEN' || kind === 'EXIT';
  }
  // Avoid ADD +0.0pp / TRIM −0.0pp from float noise or sub-0.05pp churn.
  return Number(delta.toFixed(1)) !== 0;
}

/** Format a material weight delta for Brief; null when it would read as 0.0pp. */
export function formatBriefWeightChange(event: DashboardPositionEvent): string | null {
  const delta = eventWeightDeltaPp(event);
  if (delta == null || Number(delta.toFixed(1)) === 0) return null;
  return `${delta > 0 ? '+' : ''}${delta.toFixed(1)}pp`;
}

function absDelta(event: DashboardPositionEvent): number {
  return Math.abs(eventWeightDeltaPp(event) ?? 0);
}

/** Prefer largest absolute move, then ticker for stability. */
function pickLargestMove(events: DashboardPositionEvent[]): DashboardPositionEvent | null {
  if (events.length === 0) return null;
  return [...events].sort((a, b) => {
    const bySize = absDelta(b) - absDelta(a);
    if (bySize !== 0) return bySize;
    return a.ticker.localeCompare(b.ticker);
  })[0]!;
}

/**
 * Select the Brief book-event panel row.
 *
 * Prefer a material move on `sessionDate` (book / brief as-of); else the latest
 * material change on any date. Returns null when nothing is decision-grade —
 * callers show an honest empty state instead of inventing ADD +0.0pp.
 */
export function selectBriefBookEvent(
  events: DashboardPositionEvent[] | null | undefined,
  opts?: { sessionDate?: string | null }
): DashboardPositionEvent | null {
  const material = (events ?? []).filter(isMaterialBookEvent);
  if (material.length === 0) return null;

  const byDateDesc = [...material].sort(
    (a, b) => b.date.localeCompare(a.date) || a.ticker.localeCompare(b.ticker)
  );

  const session = opts?.sessionDate?.trim() || null;
  if (session) {
    const onSession = byDateDesc.filter((e) => e.date === session);
    const pick = pickLargestMove(onSession);
    if (pick) return pick;
  }

  const latestDate = byDateDesc[0]?.date;
  if (!latestDate) return null;
  return pickLargestMove(byDateDesc.filter((e) => e.date === latestDate));
}
