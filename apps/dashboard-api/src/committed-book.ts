/**
 * Committed-book date gate for the dashboard-api worker (slice 0003).
 *
 * Server-side port of `committedBookDate` / `previousBookDate` in
 * `apps/dashboard/lib/dashboard-ssot.ts`. Contract §6.1: `book_as_of` is the
 * latest positions date on or before the committed `daily_snapshots` date —
 * null (with `not_found`) when the snapshot is missing. Never silently
 * substitute the latest position date as "committed".
 *
 * Pure logic — no I/O, no secrets, no time/tool-call budgets.
 */

function latestMatching(
  dates: readonly string[],
  keep: (date: string) => boolean,
): string | null {
  let latest: string | null = null;
  for (const date of dates) {
    if (date && keep(date) && (latest === null || date > latest)) {
      latest = date;
    }
  }
  return latest;
}

/** Latest positions date on or before the committed snapshot; otherwise null. */
export function committedBookDate(
  snapshotDate: string | null | undefined,
  positionDates: readonly string[],
): string | null {
  if (!snapshotDate) return null;
  return latestMatching(positionDates, (date) => date <= snapshotDate);
}

/** Prior book date strictly before the committed book date. */
export function previousBookDate(
  bookDate: string | null | undefined,
  positionDates: readonly string[],
): string | null {
  if (!bookDate) return null;
  return latestMatching(positionDates, (date) => date < bookDate);
}

/** True only when the booked row-set is for the snapshot date itself. */
export function bookedCoversCommittedSnapshot(
  snapshotDate: string | null | undefined,
  bookDate: string | null | undefined,
): boolean {
  return snapshotDate != null && bookDate != null && bookDate === snapshotDate;
}
