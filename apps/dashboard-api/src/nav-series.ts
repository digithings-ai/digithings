/**
 * Seam-chained NAV series for the dashboard-api worker (slice 0003).
 *
 * Server-side port of the client chain in `apps/dashboard/lib/accounting-views.ts`
 * (`navContinuityStepPct`, `chainNavContinuity`, seam helpers) plus the
 * day-return guards in `apps/dashboard/lib/performance-ssot.ts`
 * (`crossesNavSeam`, `derivedDayReturnPct`, `MAX_DAY_RETURN_GAP_DAYS`).
 * Serves contract §6.6 (`GET /nav-series`) and the §6.1 `nav_tip`
 * `day_return_pct` rule: null across NAV seams or calendar gaps > 4 days;
 * seam basis changes carry flat, never draw a phantom return.
 *
 * Pure logic — no I/O, no secrets, no time/tool-call budgets.
 */

export type NavContract = 'finalized_accounting' | 'legacy_estimate';

export interface NavInputRow {
  date: string;
  nav: number;
  dayReturnPct?: number | null;
  source?: string | null;
  contract?: string | null;
  seriesSeam?: boolean | null;
}

export interface NavSeriesPoint {
  date: string;
  nav: number;
  dayReturnPct: number | null;
  contract: NavContract;
  /** Base-100 continuity index (chained per-row steps, seam-flat). */
  index: number;
}

/** A daily step beyond this is a basis/funding artifact, not a return (#4014). */
export const CONTINUITY_MAX_STEP_PCT = 25;

/**
 * Maximum calendar-day gap for deriving a day return from adjacent NAV rows.
 * Covers a weekend + one holiday; wider gaps are finalizer holes.
 */
export const MAX_DAY_RETURN_GAP_DAYS = 4;

/** Calendar-day difference (UTC `YYYY-MM-DD` strings). later − earlier. */
export function calendarDaysBetween(earlier: string, later: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(earlier) || !/^\d{4}-\d{2}-\d{2}$/.test(later)) {
    return null;
  }
  const a = Date.UTC(+earlier.slice(0, 4), +earlier.slice(5, 7) - 1, +earlier.slice(8, 10));
  const b = Date.UTC(+later.slice(0, 4), +later.slice(5, 7) - 1, +later.slice(8, 10));
  return Math.round((b - a) / 86_400_000);
}

/** Provenance of one NAV row. Unlabeled rows are estimates — never finalized. */
export function navRowContractLabel(row: {
  source?: string | null;
  contract?: string | null;
}): NavContract {
  if (row.contract === 'finalized_accounting' || row.source === 'finalized_accounting') {
    return 'finalized_accounting';
  }
  return 'legacy_estimate';
}

/**
 * True when a NAV row sits on a legacy↔finalized seam: the explicit
 * `seriesSeam` flag or a detected source flip against the previous row.
 */
export function isNavSeriesSeam(
  row: { seriesSeam?: boolean | null; source?: string | null },
  prevSource?: string | null,
): boolean {
  if (row.seriesSeam === true) return true;
  if (prevSource == null) return false;
  const source = row.source ?? null;
  return source != null && prevSource != null && source !== prevSource;
}

/**
 * True when the tip row starts a new source run (#3767). A seam means the
 * adjacent NAV values come from two different series — deriving a return
 * across them draws a phantom jump.
 */
export function crossesNavSeam(
  tip: Pick<NavInputRow, 'source' | 'seriesSeam'>,
  prior: Pick<NavInputRow, 'source'> | null,
): boolean {
  if (!prior) return false;
  return isNavSeriesSeam(tip, prior.source ?? null);
}

/**
 * Day return for one row: the seam guard refuses stored or derived returns
 * across a source flip; otherwise prefer the row's own `dayReturnPct`, else
 * derive from levels only when the calendar gap is 1–4 days.
 */
export function derivedDayReturnPct(
  tip: Pick<NavInputRow, 'date' | 'nav' | 'dayReturnPct' | 'source' | 'seriesSeam'>,
  prior: Pick<NavInputRow, 'date' | 'nav'> & { source?: string | null } | null,
): number | null {
  if (crossesNavSeam(tip, prior)) return null;
  if (tip.dayReturnPct != null && Number.isFinite(tip.dayReturnPct)) {
    return tip.dayReturnPct;
  }
  if (!prior || !(prior.nav > 0)) return null;
  const gap = calendarDaysBetween(prior.date, tip.date);
  if (gap == null || gap < 1 || gap > MAX_DAY_RETURN_GAP_DAYS) return null;
  return (tip.nav / prior.nav - 1) * 100;
}

/**
 * Continuity step for one row, in percent (#4014): prefer the row's own day
 * return; else derive from levels only within its run; a seam row with no
 * day return carries flat; implausible steps carry flat.
 */
export function navContinuityStepPct(row: NavInputRow, previous: NavInputRow): number {
  const daily = row.dayReturnPct;
  if (daily != null && Number.isFinite(daily)) {
    return Math.abs(daily) <= CONTINUITY_MAX_STEP_PCT ? daily : 0;
  }
  if (!isNavSeriesSeam(row, previous.source ?? null) && previous.nav > 0) {
    const level = (row.nav / previous.nav - 1) * 100;
    if (Number.isFinite(level) && Math.abs(level) <= CONTINUITY_MAX_STEP_PCT) {
      return level;
    }
  }
  return 0;
}

/**
 * Base-100 continuity chain over a stitched NAV series (#4014): compounds each
 * row's own step so every tracked day shares one basis without bridging runs.
 * Sorted ascending; empty in → empty out.
 */
export function chainNavContinuity(
  rows: ReadonlyArray<NavInputRow>,
): Array<{ date: string; index: number }> {
  const sorted = [...rows]
    .filter((row) => Number.isFinite(row.nav) && row.nav > 0)
    .sort((a, b) => a.date.localeCompare(b.date));
  if (sorted.length === 0) return [];
  const chained = [{ date: sorted[0].date, index: 100 }];
  let index = 100;
  for (let position = 1; position < sorted.length; position += 1) {
    index *= 1 + navContinuityStepPct(sorted[position], sorted[position - 1]) / 100;
    chained.push({ date: sorted[position].date, index });
  }
  return chained;
}

function finiteNav(nav: number | null | undefined): nav is number {
  return nav != null && Number.isFinite(nav) && nav > 0;
}

/**
 * Full §6.6 series: per-row day returns (seam/gap-guarded), per-point
 * contract labels preserved so consumers can badge tip flips, and the
 * base-100 continuity index chained alongside.
 */
export function buildNavSeries(rows: ReadonlyArray<NavInputRow>): NavSeriesPoint[] {
  const sorted = [...rows]
    .filter((row) => finiteNav(row.nav))
    .sort((a, b) => a.date.localeCompare(b.date));
  const chained = chainNavContinuity(sorted);
  const indexByDate = new Map(chained.map((c) => [c.date, c.index]));
  return sorted.map((row, i) => ({
    date: row.date,
    nav: row.nav,
    dayReturnPct: derivedDayReturnPct(row, i === 0 ? null : sorted[i - 1]),
    contract: navRowContractLabel(row),
    index: indexByDate.get(row.date) ?? 100,
  }));
}

/**
 * Forward-fill missing calendar dates carrying the last point flat (null day
 * return, unchanged index) — only across gaps of ≤ 4 days. Wider gaps are
 * finalizer holes and stay broken. Input must be date-ascending.
 */
export function forwardFillCalendarGaps(
  points: ReadonlyArray<NavSeriesPoint>,
  maxGapDays = MAX_DAY_RETURN_GAP_DAYS,
): NavSeriesPoint[] {
  if (points.length === 0) return [];
  const out: NavSeriesPoint[] = [{ ...points[0] }];
  for (let i = 1; i < points.length; i += 1) {
    const prev = out[out.length - 1];
    const gap = calendarDaysBetween(prev.date, points[i].date);
    if (gap != null && gap > 1 && gap <= maxGapDays) {
      const base = Date.UTC(
        +prev.date.slice(0, 4),
        +prev.date.slice(5, 7) - 1,
        +prev.date.slice(8, 10),
      );
      for (let d = 1; d < gap; d += 1) {
        const filled = new Date(base + d * 86_400_000).toISOString().slice(0, 10);
        out.push({
          date: filled,
          nav: prev.nav,
          dayReturnPct: null,
          contract: prev.contract,
          index: prev.index,
        });
      }
    }
    out.push({ ...points[i] });
  }
  return out;
}
