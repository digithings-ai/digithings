/**
 * Dashboard SSOT for the committed Olympus book (#3319).
 *
 * `daily_snapshots.date` (ledger-commit / digest date) is the as-of for Brief,
 * Pipeline, decision, and holdings. Raw latest `positions` or `pm-rebalance`
 * rows that are newer than that snapshot are unpublished books — H9 can write
 * positions before `append_commit_chain` succeeds — and must not mix into the UI.
 */

/** Latest positions date on or before the committed snapshot; otherwise null. */
export function committedBookDate(
  snapshotDate: string | null | undefined,
  positionDates: Iterable<string>
): string | null {
  if (!snapshotDate) return null;
  const onOrBefore = [...new Set(positionDates)].filter((d) => !!d && d <= snapshotDate);
  if (onOrBefore.includes(snapshotDate)) return snapshotDate;
  onOrBefore.sort();
  return onOrBefore.at(-1) ?? null;
}

/** Prior book date strictly before the committed book date. */
export function previousBookDate(
  bookDate: string | null | undefined,
  positionDates: Iterable<string>
): string | null {
  if (!bookDate) return null;
  const earlier = [...new Set(positionDates)]
    .filter((d) => !!d && d < bookDate)
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
    'Newer positions are hidden until a ledger commit lands.'
  );
}
