/**
 * How old a block's data is, and what its window bar says about it.
 *
 * The defect this exists to fix: a window bar printed the run date and nothing
 * else, so a read from three weeks ago carried the same ink as a read from this
 * morning. Nothing in the frame said "behind". The tone is carried by words
 * first — the bar renders in mute, so a named state is the only severity claim
 * that does not depend on colour — and by ink second.
 *
 * Bands match the FX hub policy approved in #5047 so there is no second set of
 * numbers to reconcile: 0-1 sessions `ok`, 2 `warn`, 3+ `stale`. Weekends do not
 * count (see `trading-calendar`), so Monday morning does not warn on Friday's run.
 */
import { calendarDay, todayYmd, tradingSessionsSince } from '@/lib/trading-calendar';

export const SESSION_WARN = 2;
export const SESSION_STALE = 3;

export type BlockAge = 'ok' | 'warn' | 'stale';

/** The band a number of sessions behind the last run falls into. */
export function blockAge(sessions: number): BlockAge {
  if (sessions >= SESSION_STALE) return 'stale';
  if (sessions >= SESSION_WARN) return 'warn';
  return 'ok';
}

function ageLabel(sessions: number): string {
  if (sessions === 0) return 'current session';
  return sessions === 1 ? '1 trading day old' : `${sessions} trading days old`;
}

export type BlockAgeFooter = {
  /** Everything before the state word, including the separator when one is due. */
  lead: string;
  /** The state a footer names, or null when the pane is not aged past `ok`.
   *  An aged pane names its state; an `ok` pane does not, because
   *  "current session" already carries that claim and a trailing `· ok` is noise. */
  state: BlockAge | null;
};

export type BlockAgeInput = {
  /** The block's date, however it chose to name it. Anything that does not open
   *  with a real date is passed through un-aged rather than treated as a date. */
  runDate: string | null | undefined;
  /** Shown verbatim when there is no date to age, so an undated block looks the
   *  same as it always has. */
  route: string;
  /** Injectable clock; defaults to the reader's today. */
  now?: string;
};

/**
 * The window-bar text for one block, as parts so the caller can ink the state
 * word without re-parsing the sentence.
 */
export function blockAgeFooter({ runDate, route, now = todayYmd() }: BlockAgeInput): BlockAgeFooter {
  const raw = typeof runDate === 'string' ? runDate.trim() : '';
  // No date at all: claim nothing and keep the route this block always showed.
  if (raw === '') return { lead: route, state: null };

  const day = calendarDay(raw);
  // Not a session-bearing date — an id, a window range. Several blocks pass such
  // values deliberately, so print them as they read and claim no age.
  if (day === null) return { lead: `as of ${raw}`, state: null };

  const sessions = tradingSessionsSince(day, now);
  // The clock is unreadable, so there is no honest age to report.
  if (sessions === null) return { lead: `as of ${day}`, state: null };

  // A run dated ahead of the clock is skew or a bad write, not proof of
  // staleness, so no band is claimed. But "current session" is a positive claim
  // about freshness that this one cannot support: show the date and stop.
  // Both ends are normalised YYYY-MM-DD, so the string compare is the date compare.
  const today = calendarDay(now);
  if (today !== null && day > today) return { lead: `as of ${day}`, state: null };

  const age = blockAge(sessions);
  return {
    lead: `as of ${day} · ${ageLabel(sessions)}${age === 'ok' ? '' : ' · '}`,
    state: age === 'ok' ? null : age,
  };
}

/** The footer as one flat string — what the bar reads, and what tests assert. */
export function blockAgeText(footer: BlockAgeFooter): string {
  return footer.state === null ? footer.lead : `${footer.lead}${footer.state}`;
}
