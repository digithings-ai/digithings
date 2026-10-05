/**
 * Research runs MON-FRI, so age is counted in trading sessions rather than
 * hours. A Friday run read on a Sunday has not gone stale: no session was due in
 * between. `Date.now() - 24h` would raise that false alarm every weekend and
 * teach the reader to ignore the tone.
 *
 * This is the app-side copy of `clients/digiquant-tui/src/pages/trading-calendar.ts`
 * (added by #5047). The two surfaces render age independently and neither app
 * imports the TUI, so the helper is duplicated deliberately rather than given a
 * shared home in `packages/` — that move is its own leaf.
 *
 * Public holidays are not modelled here. They belong to the venue-aware session
 * calendar in ADR 0013 (`trading_calendar(date, venue)`, epic #335); this is the
 * weekday skeleton that calendar refines.
 */

// One whole calendar day, optionally carrying a time of day that is dropped.
// Anchored at both ends on purpose: the TUI copy this is ported from only pins
// the prefix, because every stamp it reads is a single date off a structured
// field. Here `asOf` also names window ranges (`start → end`) and record ids,
// and a prefix match would read `2026-09-14 → 2026-09-30` as 2026-09-14 — ageing
// a block by its window's *start* and calling an in-flight window stale. A
// space only counts as a separator when a time follows, so ` → ` is not one.
const YMD = /^(\d{4})-(\d{2})-(\d{2})(?:[T ]\d{1,2}:\d{2}.*)?$/;
const DAY_MS = 86_400_000;

function parseYmd(value: string | null | undefined): number | null {
  if (typeof value !== 'string') return null;
  const match = YMD.exec(value.trim());
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  const ms = Date.UTC(year, month - 1, day);
  const date = new Date(ms);
  // Date.UTC would roll 2026-02-30 over into March; compare the round trip so an
  // impossible date reads as unreadable rather than as a real, different day.
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
    return null;
  }
  return ms;
}

/**
 * Weekdays only. This is right for the equity and FX venues the app shows today
 * (every market block defaults to `MK_DEFAULT_SYMBOL`, an equity), but ADR 0013
 * also lists a `CRYPTO` venue that trades 24/7 — a Saturday there is a session,
 * not a rest day, and a Friday crypto run would read "current session" a day
 * late. Thread the payload's `venue` through here once that table exists rather
 * than widening this function with a guess.
 */
const isWeekday = (ms: number) => {
  const weekday = new Date(ms).getUTCDay();
  return weekday !== 0 && weekday !== 6;
};

/**
 * Trading sessions in the half-open range `(runDate, now]`, weekdays only.
 *
 * Returns `0` when `now` is at or before `runDate`: a run dated ahead of the
 * clock is skew or a bad write, not staleness. Returns `null` when either end is
 * unreadable, so callers can tell "no age" apart from "zero age".
 */
export function tradingSessionsSince(runDate: string, now: string): number | null {
  const from = parseYmd(runDate);
  const to = parseYmd(now);
  if (from === null || to === null) return null;
  if (to <= from) return 0;
  let sessions = 0;
  for (let cursor = from + DAY_MS; cursor <= to; cursor += DAY_MS) {
    if (isWeekday(cursor)) sessions += 1;
  }
  return sessions;
}

/** The reader's own calendar day as `YYYY-MM-DD`. */
export function todayYmd(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

/** Normalise a value to `YYYY-MM-DD`, or null when it is not exactly one date.
 *  A timestamp is reduced to its date; a range, an id or an impossible day is
 *  rejected rather than read as its first token. */
export function calendarDay(value: string | null | undefined): string | null {
  return parseYmd(value) === null ? null : (value as string).trim().slice(0, 10);
}
