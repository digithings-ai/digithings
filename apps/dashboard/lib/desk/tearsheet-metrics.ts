/**
 * Tearsheet headline honesty. Alpha and IR stay an em dash under 20 overlap
 * days (CONTRACT §6.4). This does not recompute the series.
 */
import { MIN_OVERLAP_DAYS } from '@digithings/ui';

export const TEARSHEET_MIN_OVERLAP_DAYS = MIN_OVERLAP_DAYS;

export const TEARSHEET_MISSING = '—';

export function formatOverlapGatedMetric(
  value: number | null | undefined,
  overlapDays: number,
): string {
  if (overlapDays < TEARSHEET_MIN_OVERLAP_DAYS) return TEARSHEET_MISSING;
  if (value == null || !Number.isFinite(value)) return TEARSHEET_MISSING;
  const sign = value > 0 ? '+' : '';
  return `${sign}${value}`;
}
