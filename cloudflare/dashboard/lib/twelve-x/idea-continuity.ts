/**
 * Pair+direction continuity across consecutive idea boards.
 *
 * Ideas are keyed by (run_date, rank) with no stable ID. We treat the same
 * normalized pair+direction on consecutive boards that have ideas as one
 * "thread": first_suggested = start of that streak, last_updated = this row's as_of.
 */

export type IdeaContinuityKey = string;

export interface IdeaContinuityMeta {
  /** Earliest run_date in the unbroken pair+direction streak ending on this board. */
  firstSuggested: string;
  /** Publish timestamp for this board's row. */
  lastUpdated: string;
  /** Number of boards (inclusive) in the streak. */
  boardsOnThread: number;
}

export interface IdeaContinuityInput {
  run_date: string;
  pair: string;
  direction: string;
  as_of: string;
}

/** Normalize pair/direction so "usd/jpy" + "Long" match across boards. */
export function continuityKey(pair: string, direction: string): IdeaContinuityKey {
  const p = pair.trim().toUpperCase().replace(/\s+/g, '');
  const d = direction.trim().toLowerCase();
  return `${p}|${d}`;
}

/**
 * Build continuity for each idea on `boardDate` from full history rows.
 * History may include other dates; only consecutive boards (sorted unique
 * run_dates that have any ideas) count toward the streak.
 */
export function continuityForBoard(
  boardDate: string,
  history: readonly IdeaContinuityInput[],
): Map<IdeaContinuityKey, IdeaContinuityMeta> {
  const out = new Map<IdeaContinuityKey, IdeaContinuityMeta>();
  if (!boardDate || history.length === 0) return out;

  const boards = [...new Set(history.map((h) => h.run_date))].sort();
  const boardIdx = boards.indexOf(boardDate);
  if (boardIdx < 0) return out;

  const keysOnBoard = new Map<IdeaContinuityKey, string>();
  for (const row of history) {
    if (row.run_date !== boardDate) continue;
    const key = continuityKey(row.pair, row.direction);
    // Prefer the earliest as_of if multiple ranks share pair+direction (rare).
    const prev = keysOnBoard.get(key);
    if (!prev || row.as_of < prev) keysOnBoard.set(key, row.as_of);
  }

  for (const [key, lastUpdated] of keysOnBoard) {
    let first = boardDate;
    let boardsOnThread = 1;
    for (let i = boardIdx - 1; i >= 0; i--) {
      const d = boards[i]!;
      const present = history.some(
        (h) => h.run_date === d && continuityKey(h.pair, h.direction) === key,
      );
      if (!present) break;
      first = d;
      boardsOnThread += 1;
    }
    out.set(key, { firstSuggested: first, lastUpdated, boardsOnThread });
  }

  return out;
}

/** Compact board date: "12 Aug". */
export function formatBoardDate(isoDate: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!m) return isoDate;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const month = months[Number(m[2]) - 1] ?? m[2];
  return `${Number(m[3])} ${month}`;
}

/** Compact publish time in UTC: "19 Aug 12:37 UTC". */
export function formatPublishAsOf(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const day = d.getUTCDate();
  const month = months[d.getUTCMonth()] ?? '';
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${day} ${month} ${hh}:${mm} UTC`;
}

export function formatContinuityLine(meta: IdeaContinuityMeta): string {
  const first = formatBoardDate(meta.firstSuggested);
  const updated = formatPublishAsOf(meta.lastUpdated);
  if (meta.boardsOnThread <= 1) {
    return `Suggested ${first} · Updated ${updated}`;
  }
  return `First suggested ${first} · Updated ${updated}`;
}
