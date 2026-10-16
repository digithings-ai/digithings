/**
 * NAV source-run seam helpers (#3767 / #3935) for the digiquant.io live layer.
 *
 * `public_accounting_nav_history` stitches legacy estimates to finalized
 * accounting and marks the first row after a source flip with an additive
 * boolean `series_seam` (migration 123). Returns must be rebased on the current
 * source run — bridging a seam draws a phantom jump (the false Sep-8 ~+10%).
 *
 * Mirrors the dashboard `lib/accounting-views.ts` semantics so both surfaces
 * agree; kept local because digiquant-web cannot import dashboard code.
 */

export interface NavSeamRow {
  date: string;
  source?: string | null;
  /** Migration 123: true on the first row after a legacy↔finalized flip. */
  seriesSeam?: boolean | null;
}

/**
 * True when a row starts a new source run: the explicit `series_seam` flag, or
 * a detected change of `source` versus the previous row (when both are labeled).
 */
export function isNavSeriesSeam(
  row: { seriesSeam?: boolean | null; source?: string | null },
  prevSource?: string | null,
): boolean {
  if (row.seriesSeam === true) return true;
  if (prevSource == null) return false;
  const source = row.source ?? null;
  return source != null && source !== prevSource;
}

/**
 * Dates where the stitched NAV series flips source (#3767). Charts and KPIs use
 * these dates to break the series instead of drawing a phantom return across it.
 */
export function findNavSeriesSeams(rows: ReadonlyArray<NavSeamRow>): string[] {
  const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
  const seams: string[] = [];
  let prevSource: string | null | undefined;
  for (const row of sorted) {
    if (prevSource !== undefined && isNavSeriesSeam(row, prevSource)) {
      seams.push(row.date);
    }
    prevSource = row.source ?? null;
  }
  return seams;
}

/**
 * Rows of the most recent source run (#3767 / #3935). A stitched series can
 * hold several runs (legacy → finalized → …); returns are rebased on the current
 * run, never computed across a seam. Sorted ascending; falls back to the full
 * series when a seam date is absent. Empty in → empty out.
 */
export function currentNavRun<T extends NavSeamRow>(rows: ReadonlyArray<T>): T[] {
  if (rows.length === 0) return [];
  const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
  const seams = findNavSeriesSeams(sorted);
  if (seams.length === 0) return sorted;
  const current = sorted.filter((row) => row.date >= seams[seams.length - 1]);
  return current.length ? current : sorted;
}
