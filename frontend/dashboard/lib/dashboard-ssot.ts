/**
 * Committed-book SSOT: Brief, Pipeline, pm-rebalance, and holdings follow
 * `daily_snapshots.date`. Positions newer than that snapshot are unpublished
 * and must not mix into the UI.
 */

/** Latest positions date on or before the committed snapshot; otherwise null. */
export function committedBookDate(
  snapshotDate: string | null | undefined,
  positionDates: Iterable<string>
): string | null {
  if (!snapshotDate) return null;
  const onOrBefore = [...new Set(positionDates)]
    .filter((d) => d && d <= snapshotDate)
    .sort();
  return onOrBefore.at(-1) ?? null;
}

/** Prior book date strictly before the committed book date. */
export function previousBookDate(
  bookDate: string | null | undefined,
  positionDates: Iterable<string>
): string | null {
  if (!bookDate) return null;
  const earlier = [...new Set(positionDates)]
    .filter((d) => d && d < bookDate)
    .sort();
  return earlier.at(-1) ?? null;
}

/** True only when the booked positions row-set is for the snapshot date itself. */
export function bookedCoversCommittedSnapshot(
  snapshotDate: string | null | undefined,
  bookDate: string | null | undefined
): boolean {
  return snapshotDate != null && bookDate != null && bookDate === snapshotDate;
}

export function unpublishedBookNote(
  snapshotDate: string | null | undefined,
  todayYmd: string
): string | null {
  if (!snapshotDate || snapshotDate >= todayYmd) return null;
  return (
    `Last committed snapshot is ${snapshotDate}. ` +
    'Newer positions are hidden until a snapshot exists for that date.'
  );
}
