/**
 * Committed-book SSOT: Brief, Pipeline, pm-rebalance, and holdings follow
 * `daily_snapshots.date`. Positions newer than that snapshot stay unpublished.
 */

function latestMatching(
  dates: Iterable<string>,
  keep: (date: string) => boolean
): string | null {
  const matching = [...new Set(dates)].filter((date) => date && keep(date)).sort();
  return matching.at(-1) ?? null;
}

/** Latest positions date on or before the committed snapshot; otherwise null. */
export function committedBookDate(
  snapshotDate: string | null | undefined,
  positionDates: Iterable<string>
): string | null {
  if (!snapshotDate) return null;
  return latestMatching(positionDates, (date) => date <= snapshotDate);
}

/** Prior book date strictly before the committed book date. */
export function previousBookDate(
  bookDate: string | null | undefined,
  positionDates: Iterable<string>
): string | null {
  if (!bookDate) return null;
  return latestMatching(positionDates, (date) => date < bookDate);
}

/** True only when the booked positions row-set is for the snapshot date itself. */
export function bookedCoversCommittedSnapshot(
  snapshotDate: string | null | undefined,
  bookDate: string | null | undefined
): boolean {
  return snapshotDate != null && bookDate != null && bookDate === snapshotDate;
}

/** Operator copy when a position date is newer than the committed snapshot. */
export function unpublishedBookNote(
  snapshotDate: string | null | undefined,
  positionDates: Iterable<string>
): string | null {
  if (!snapshotDate) return null;
  for (const date of positionDates) {
    if (date && date > snapshotDate) {
      return (
        `Last committed snapshot is ${snapshotDate}. ` +
        'Newer positions are hidden until a snapshot exists for that date.'
      );
    }
  }
  return null;
}

/** Throw when the latest daily_snapshots query failed. */
export function assertDailySnapshotQueryOk(error: unknown): void {
  if (!error) return;
  let detail: string;
  if (error instanceof Error) {
    detail = error.message;
  } else if (typeof error === 'object' && 'message' in error) {
    detail = String(error.message);
  } else {
    detail = String(error);
  }
  throw new Error(`Daily snapshot query failed: ${detail}`);
}
