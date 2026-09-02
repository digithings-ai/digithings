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

/**
 * Operator copy when unpublished positions exist past the committed snapshot.
 * Driven by `snapshot.date` vs position dates — not calendar-today (weekends
 * and holidays must not fire this just because the snapshot is older than today).
 * `_todayYmd` stays on the contract so Brief can pass `formatYmd(now)`; it is not a trigger.
 */
export function unpublishedBookNote(
  snapshotDate: string | null | undefined,
  positionDates: Iterable<string>,
  _todayYmd: string
): string | null {
  if (!snapshotDate) return null;
  const hasNewerPosition = [...new Set(positionDates)].some((d) => Boolean(d) && d > snapshotDate);
  if (!hasNewerPosition) return null;
  return (
    `Last committed snapshot is ${snapshotDate}. ` +
    'Newer positions are hidden until a snapshot exists for that date.'
  );
}

/** Throw when the latest daily_snapshots query failed — never treat an error as an empty snapshot. */
export function assertDailySnapshotQueryOk(error: unknown): void {
  if (!error) return;
  const detail =
    error && typeof error === 'object' && 'message' in error
      ? String((error as { message: unknown }).message)
      : error instanceof Error
        ? error.message
        : String(error);
  throw new Error(`Daily snapshot query failed: ${detail}`);
}
