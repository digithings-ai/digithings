/**
 * Shared number formatting for the twelve-x surfaces, so score and effective-n
 * rendering cannot drift between the panels, tables, and drilldowns.
 */

/** Signed 2-dp score (`+1.23` / `-0.45`); em dash for null or non-finite. */
export function fmtSigned(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
}

/** Effective n: integer verbatim, else 1-dp; em dash for null or non-finite. */
export function fmtNEff(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}
