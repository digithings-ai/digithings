/**
 * Publish-generation guard for the generation-stamped twelve-x snapshot tables
 * (`fx_consensus_snapshot`, `fx_confluence_snapshot`, `fx_events_snapshot`).
 *
 * A rerun of one `run_date` publishes a second generation of rows next to the
 * first. One publish stamps every row of that date with an identical `as_of`,
 * so the generation of a row is read off its stamp. These helpers are the one
 * place that reads it, so every reader resolves the same generation.
 *
 * Rules the whole module keeps:
 * - `as_of` is `timestamptz`. It is compared as epoch milliseconds through
 *   `Date.parse`, never as a string: string order is not guaranteed across
 *   offsets, and the stamps arrive with 6 fractional-second digits.
 * - No input array is mutated. Callers hand in arrays they still own, and every
 *   function returns a new array that keeps the relative order of its input.
 * - Only the newest stamp wins. On an equal stamp the incumbent — the row seen
 *   first — wins, so one call returns the same rows for the same input. Two rows
 *   that share a stamp belong to one generation, so which of the two survives
 *   only picks which duplicate the reader sees, never which generation.
 * - A row without a usable stamp is kept only while its group has no usable
 *   stamp at all. An unusable stamp never hides a stamped row.
 *
 * Pure on purpose: no Supabase import lives here. The anchor-then-filter read
 * helper is a separate module.
 */

/** Every generation-stamped twelve-x snapshot row carries these two. */
export interface GenerationStamped {
  run_date: string;
  as_of?: string | null;
}

/** One publish = 15 min, the same constant getTradeIdeas already uses. */
export const SNAPSHOT_PUBLISH_WINDOW_MS = 15 * 60 * 1000;

/** Epoch ms for as_of. NaN when missing or unparseable — never throws. */
export function asOfMs(row: { as_of?: string | null }): number {
  if (typeof row?.as_of !== 'string') return Number.NaN;
  const stamp = row.as_of.trim();
  if (stamp === '') return Number.NaN;
  const ms = Date.parse(stamp);
  return Number.isNaN(ms) ? Number.NaN : ms;
}

/** Newest usable as_of over rows, or null when none is usable. */
export function newestAsOfMs(rows: GenerationStamped[]): number | null {
  let newest: number | null = null;
  for (const row of rows) {
    const ms = asOfMs(row);
    if (Number.isNaN(ms)) continue;
    if (newest === null || ms > newest) newest = ms;
  }
  return newest;
}

/**
 * Publish-window filter for single-date readers. Keeps rows stamped within
 * SNAPSHOT_PUBLISH_WINDOW_MS of the newest stamp, edge included. Rows with no
 * usable stamp are dropped when at least one usable stamp exists, and kept when
 * none does.
 *
 * Two limits the caller must know. The rows must all belong to one run_date — a
 * batch spanning several dates collapses onto its newest stamp. And two publishes
 * less than one window apart still blend, which is why this is the fallback and
 * not the primary filter: the closest two generations ever observed are 3.63 h
 * apart, and the anchor-then-filter read filters on the stamp itself.
 */
export function keepNewestPublish<T extends GenerationStamped>(
  rows: T[],
  windowMs: number = SNAPSHOT_PUBLISH_WINDOW_MS,
): T[] {
  const newest = newestAsOfMs(rows);
  if (newest === null) return rows.slice();
  const oldestKept = newest - windowMs;
  return rows.filter((row) => {
    const ms = asOfMs(row);
    return !Number.isNaN(ms) && ms >= oldestKept;
  });
}

/**
 * Newest generation per (run_date, currency) for unbounded series readers.
 * A date whose currencies were only partly republished keeps the unrepublished
 * currencies rather than losing them, so the series has no false gap.
 *
 * The series key is exactly (run_date, currency). A table keyed on something
 * else needs its own reader, not a different key here.
 */
export function keepNewestGenerationPerSeriesKey<
  T extends GenerationStamped & { currency: string },
>(rows: T[]): T[] {
  const winners = new Map<string, number>();
  for (let i = 0; i < rows.length; i += 1) {
    const row = rows[i];
    const key = seriesKey(row);
    const incumbentIndex = winners.get(key);
    if (incumbentIndex === undefined) {
      winners.set(key, i);
      continue;
    }
    if (isNewer(row, rows[incumbentIndex])) winners.set(key, i);
  }
  return rows.filter((row, i) => winners.get(seriesKey(row)) === i);
}

/** Two group keys can never collide: a currency may hold any character. */
function seriesKey(row: GenerationStamped & { currency: string }): string {
  return JSON.stringify([row.run_date, row.currency]);
}

/** True when candidate supersedes incumbent: newer stamp, or any stamp over none. */
function isNewer(
  candidate: GenerationStamped,
  incumbent: GenerationStamped,
): boolean {
  const candidateMs = asOfMs(candidate);
  if (Number.isNaN(candidateMs)) return false;
  const incumbentMs = asOfMs(incumbent);
  return Number.isNaN(incumbentMs) || candidateMs > incumbentMs;
}