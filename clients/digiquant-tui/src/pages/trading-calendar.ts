/**
 * FX research runs MON-FRI, so age is counted in trading sessions rather than
 * hours. A Friday run read on a Sunday has not gone stale: no session was due
 * in between. `Date.now() - 24h` would raise that false alarm every weekend and
 * teach the reader to ignore the tone.
 *
 * Public holidays are not modelled here. They belong to the session calendar in
 * DIG-54; this is the weekday skeleton that calendar refines.
 */

/** Calendar dates only. A time-of-day suffix is accepted and dropped. */
const YMD = /^(\d{4})-(\d{2})-(\d{2})/;

const DAY_MS = 86_400_000;

/** Midnight UTC of `value`, or null when it is not a real date.
 *  `Date.UTC` normalises impossible dates (2026-02-30 becomes 03-02), so the
 *  round-trip check rejects them. */
function parseYmd(value: string | null | undefined): number | null {
  if (typeof value !== "string") return null;
  const match = YMD.exec(value.trim());
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  const ms = Date.UTC(year, month - 1, day);
  const date = new Date(ms);
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
  return ms;
}

const isWeekday = (ms: number): boolean => {
  const weekday = new Date(ms).getUTCDay();
  return weekday !== 0 && weekday !== 6;
};

/**
 * Trading sessions a new run should have replaced by `now`, counted over the
 * half-open range `(runDate, now]`. Zero means the last run is still the one due;
 * one means the next session has come and gone or is due now.
 *
 * Returns null when either end is not a real date, so a caller can leave the
 * pane alone instead of aging it against a guess. A run dated in the future is
 * zero: clock skew is not a staleness signal.
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

/** Today in the reader's own timezone, as `YYYY-MM-DD`. */
export function todayYmd(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

/** The calendar day of `value`, normalised, or null when unreadable. */
export function calendarDay(value: string | null | undefined): string | null {
  return parseYmd(value) === null ? null : (value as string).trim().slice(0, 10);
}