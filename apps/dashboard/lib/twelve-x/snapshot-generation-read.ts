/**
 * Anchor-then-filter read helper for the five single-date readers of the
 * generation-stamped twelve-x snapshot tables (`fx_confluence_snapshot`,
 * `fx_events_snapshot`, `fx_consensus_snapshot`).
 *
 * Leaf 1's `snapshot-generation.ts` resolves a generation in the CLIENT, from a
 * publish time window. That is the right tool for a read that already has every
 * row in hand. It is the wrong tool for a reader that pins one `run_date` and
 * carries a `limit`: the surplus generation competes for the limit inside
 * PostgREST, so a limit consumed by stale rows can push the newest generation
 * off the result entirely.
 *
 * So these readers resolve the generation in SQL instead, in two round trips:
 *
 * 1. the anchor — newest `as_of` for this `run_date`, one row;
 * 2. the main read, filtered on that exact stamp.
 *
 * Three rules the module keeps:
 *
 * - The stamp is used **verbatim**. It is never re-serialised. `as_of` is a
 *   `timestamptz` carrying 6 fractional-second digits; a `Date.parse` /
 *   `toISOString` round trip truncates to milliseconds and mangles the offset,
 *   and the equality then matches nothing. This helper uses `Date.parse` only to
 *   decide whether a stamp is USABLE, never to produce one.
 * - **No anchor degrades, it does not empty.** No rows, or no usable stamp, means
 *   the main query runs unanchored — today's behaviour. An empty client panel is
 *   a worse failure than a blended one.
 * - **The fallback is never silent.** A silently-blended board is exactly the
 *   defect this issue exists to close, so the fallback path warns. Table name
 *   and run_date only: no score, no row content, nothing client-facing.
 *
 * Like leaf 1's module, this one imports no Supabase client. The query runner
 * is injected, and the runner — not this module — decides which client the query
 * is built against, so there is exactly one source of truth for the client. The
 * read shape is therefore testable without a network, and the retry/empty
 * semantics of `querySupabase` stay in the one function that owns them.
 */

import type { SupabaseClient } from '@supabase/supabase-js';
import {
  keepNewestGenerationPerSeriesKey,
  keepNewestPublish,
  type GenerationStamped,
} from './snapshot-generation';

/** One awaited query, shaped the way `querySupabase` consumes it. */
type QueryResult<R> = { data: R | null; error: unknown };

/**
 * Executes one query FROM A THUNK. In `fetch.ts` this is `querySupabase`, passed
 * in rather than reimplemented so the retry budget, the throw-on-error and the
 * `null`-means-empty rule stay in the one function that owns them.
 *
 * It receives a builder thunk, not a built query, and supplies the client itself.
 */
export type QueryRunner = <R>(
  query: (client: SupabaseClient) => PromiseLike<QueryResult<R>>,
) => Promise<R>;

export interface AnchoredReadOptions<T> {
  /** Table being read. Used for the anchor query and in the fallback warning. */
  table: string;
  /** The pinned run_date. */
  runDate: string;
  /** Executes each query. `querySupabase` in every production call site. */
  run: QueryRunner;
  /**
   * The main query. `anchor` is the verbatim stamp, or `null` on the fallback
   * path — a builder must then apply no `as_of` equality at all.
   */
  build: (
    client: SupabaseClient,
    anchor: string | null,
  ) => PromiseLike<QueryResult<T[]>>;
}

export interface SeriesReadOptions<T> {
  run: QueryRunner;
  /** The single query. No anchor: these reads carry no limit. */
  build: (client: SupabaseClient) => PromiseLike<QueryResult<T[]>>;
}

/**
 * Read one run_date, resolving its generation in SQL.
 *
 * The result is additionally passed through `keepNewestPublish`, which is the
 * defence in depth for a publish whose rows are not perfectly uniform in
 * `as_of`: the equality filter already pins one generation, and the window
 * filter catches the case where it did not.
 */
export async function readNewestGeneration<T extends GenerationStamped>(
  options: AnchoredReadOptions<T>,
): Promise<T[]> {
  const { table, runDate, run, build } = options;
  const anchor = await resolveGenerationAnchor(table, runDate, run);
  if (anchor === null) {
    console.warn(
      `[twelve-x] ${table}: no generation anchor for run_date ${runDate}; ` +
        'reading unanchored, so the result may span generations.',
    );
  }
  const rows = await run<T[]>((sb) => build(sb, anchor));
  return keepNewestPublish(rows ?? []);
}

/**
 * Read an unbounded series, resolving one generation per (run_date, currency)
 * in the client.
 *
 * For a read with no limit the surplus cannot be paged away, and an anchor query
 * would buy nothing: the main read already returns every generation, and
 * `keepNewestGenerationPerSeriesKey` picks the newest per series key from that
 * one round trip. A date whose currencies were only partly republished keeps its
 * unrepublished currencies rather than losing them, so the series has no false
 * gap.
 */
export async function readNewestGenerationPerCurrency<
  T extends GenerationStamped & { currency: string },
>(options: SeriesReadOptions<T>): Promise<T[]> {
  const { run, build } = options;
  const rows = await run<T[]>((sb) => build(sb));
  return keepNewestGenerationPerSeriesKey(rows ?? []);
}

/**
 * The newest usable `as_of` for one run_date, or `null`.
 *
 * Returns the stamp the database sent, untouched. `null` covers all three
 * fallback causes: the date has no rows, the single row carries no stamp, and
 * the stamp is not parseable. Whitespace around a stamp is treated as no stamp,
 * because forwarding it verbatim would filter on a string the database never
 * wrote.
 */
async function resolveGenerationAnchor(
  table: string,
  runDate: string,
  run: QueryRunner,
): Promise<string | null> {
  const anchors = await run<{ as_of?: string | null }[]>((sb) =>
    sb
      .from(table)
      .select('as_of')
      .eq('run_date', runDate)
      .order('as_of', { ascending: false })
      .limit(1),
  );
  const stamp = anchors?.[0]?.as_of;
  if (typeof stamp !== 'string') return null;
  const trimmed = stamp.trim();
  if (trimmed === '' || Number.isNaN(Date.parse(trimmed))) return null;
  return trimmed;
}