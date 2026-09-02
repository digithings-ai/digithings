/**
 * Committed-book SSOT: Brief, Pipeline, pm-rebalance, and holdings follow
 * `daily_snapshots.date`. Positions newer than that snapshot stay unpublished.
 */

function latestMatching(
  dates: Iterable<string>,
  keep: (date: string) => boolean
): string | null {
  let latest: string | null = null;
  for (const date of dates) {
    if (date && keep(date) && (latest === null || date > latest)) {
      latest = date;
    }
  }
  return latest;
}

function queryErrorDetail(error: unknown): string {
  if (typeof error === 'object' && error && 'message' in error) {
    return String(error.message);
  }
  return String(error);
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
  if (!snapshotDate || !latestMatching(positionDates, (date) => date > snapshotDate)) {
    return null;
  }
  return (
    `Last committed snapshot is ${snapshotDate}. ` +
    'Newer positions are hidden until a snapshot exists for that date.'
  );
}

/** Throw when the latest daily_snapshots query failed. */
export function assertDailySnapshotQueryOk(error: unknown): void {
  if (error) throw new Error(`Daily snapshot query failed: ${queryErrorDetail(error)}`);
}
