/**
 * How many starts a cron owes on one UTC day.
 *
 * Pure: no `Env`, no I/O, no cron library. Every alarm compares its observed
 * starts against this number, so a missing start becomes a count and not an
 * opinion.
 */

/** One parsed cron field. `wildcard` records whether the field was `*`. */
type Field = { values: Set<number>; wildcard: boolean };

const MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(" ");
const WEEKDAYS = "SUN MON TUE WED THU FRI SAT".split(" ");

/** Parse one field: `*`, `*\/n`, `a-b`, `a-b/n`, `a/n`, comma lists, names. */
function parseField(
  field: string,
  min: number,
  max: number,
  names: string[],
  base: number,
  wrap: number,
): Field {
  const num = (token: string): number => {
    const at = names.indexOf(token.toUpperCase());
    return at < 0 ? Number(token) : at + base;
  };
  const values = new Set<number>();
  let wildcard = true;
  for (const part of field.split(",")) {
    const [range, stepText] = part.split("/");
    const step = stepText === undefined ? 1 : Number(stepText);
    let lo: number;
    let hi: number;
    if (range === "*") {
      lo = min;
      hi = max;
    } else if (range.includes("-")) {
      [lo, hi] = range.split("-").map(num);
    } else {
      lo = num(range);
      hi = stepText === undefined ? lo : max;
    }
    if (range !== "*") wildcard = false;
    // wrap=7 folds the traditional Sunday=7 onto Sunday=0.
    for (let value = lo; value <= hi; value += step) values.add(wrap ? value % wrap : value);
  }
  return { values, wildcard };
}

/** minute, hour, day-of-month, month, day-of-week. */
function parseCron(cron: string): [Field, Field, Field, Field, Field] {
  const f = cron.trim().split(/\s+/);
  return [
    parseField(f[0], 0, 59, [], 0, 0),
    parseField(f[1], 0, 23, [], 0, 0),
    parseField(f[2], 1, 31, [], 0, 0),
    parseField(f[3], 1, 12, MONTHS, 1, 0),
    parseField(f[4], 0, 7, WEEKDAYS, 0, 7),
  ];
}

/**
 * Number of times `cron` fires on the UTC day `day` (`YYYY-MM-DD`).
 *
 * On the UTC day that contains `now`, only the minutes strictly before `now`
 * count, so today's number never reports starts that have not happened yet.
 */
export function expectedCount(cron: string, day: string, opts?: { now?: Date }): number {
  const [minute, hour, dom, month, dow] = parseCron(cron);
  const now = opts?.now ?? new Date();
  const [year, monthOfDay, dateOfMonth] = day.split("-").map(Number);
  if (!month.values.has(monthOfDay)) return 0;

  const domMatch = dom.values.has(dateOfMonth);
  const dowMatch = dow.values.has(new Date(Date.UTC(year, monthOfDay - 1, dateOfMonth)).getUTCDay());
  // cron's own rule: when both day fields are restricted, either one matching
  // is enough. With only one restricted, that one alone decides.
  const dayMatches =
    dom.wildcard && dow.wildcard
      ? true
      : !dom.wildcard && !dow.wildcard
        ? domMatch || dowMatch
        : domMatch && dowMatch;
  if (!dayMatches) return 0;

  const cutoff =
    now.toISOString().slice(0, 10) === day ? now.getUTCHours() * 60 + now.getUTCMinutes() : 1440;
  let count = 0;
  for (const h of hour.values) {
    for (const m of minute.values) {
      if (h * 60 + m < cutoff) count += 1;
    }
  }
  return count;
}