/**
 * How many starts a cron owes on one UTC day. Pure: no `Env`, no I/O, no cron
 * library. Every alarm compares its observed starts against this number, so a
 * missing start becomes a count and not an opinion.
 */

/** One parsed cron field. `wildcard` records whether the field was `*`. */
type Field = { values: Set<number>; wildcard: boolean };

const MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(" ");
const WEEKDAYS = "SUN MON TUE WED THU FRI SAT".split(" ");
const DAY_SECONDS = 86400;

/** Cloudflare schedules with Quartz, not Vixie. Every construct below parses
 *  here into a plausible wrong number or an empty set, so a silent wrong count
 *  is worse than a refusal: name the cron and the construct, then throw. */
const REFUSED = /\b(L|LW|\d+W)\b|\d#\d|\b\d{1,2}L\b/;

function refuse(cron: string, construct: string): never {
  throw new Error(`expectedCount: unsupported cron construct ${construct} in "${cron}"`);
}

/** Parse one field: `*`, `*\/n`, `a-b`, `a-b/n`, `a/n`, comma lists, names. */
function parseField(
  cron: string,
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
  if (REFUSED.test(field)) refuse(cron, field);
  if (field.includes("-") && field.includes(",")) refuse(cron, `wrapping range ${field}`);
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
    // `*/0` never advances the loop below, and a fractional or negative step
    // makes the count depend on float error.
    if (!Number.isInteger(step) || step < 1) refuse(cron, `step ${stepText} in ${part}`);
    if (range !== "*") wildcard = false;
    // wrap=7 folds the traditional Sunday=7 onto Sunday=0.
    for (let value = lo; value <= hi; value += step) {
      if (value < min || value > max) refuse(cron, `${value} in ${part} is outside ${min}-${max}`);
      values.add(wrap ? value % wrap : value);
    }
  }
  return { values, wildcard };
}

/** Number of times `cron` fires on the UTC day `day` (`YYYY-MM-DD`).
 *
 * On the UTC day that contains `now`, a minute is owed once `now` has reached
 * it, so today's number never reports starts that have not happened yet. A day
 * that has not arrived owes nothing at all.
 */
export function expectedCount(cron: string, day: string, opts?: { now?: Date }): number {
  const f = cron.trim().split(/\s+/);
  if (f.length !== 5) refuse(cron, `${f.length} fields instead of 5`);
  // Cloudflare counts 1=Sunday and rejects 0, so a numeric weekday is never the
  // day this parser would read it as.
  if (/^\s*\d+\s*$/.test(f[4])) refuse(cron, `numeric weekday ${f[4]}`);
  const minute = parseField(cron, f[0], 0, 59, [], 0, 0);
  const hour = parseField(cron, f[1], 0, 23, [], 0, 0);
  // Cloudflare ors a stepped day field instead of intersecting it, which is the
  // opposite of what the dom/dow rule below does.
  if (f[2].includes("/")) refuse(cron, `step on day-of-month ${f[2]}`);
  const dom = parseField(cron, f[2], 1, 31, [], 0, 0);
  const month = parseField(cron, f[3], 1, 12, MONTHS, 1, 0);
  const dow = parseField(cron, f[4], 0, 7, WEEKDAYS, 0, 7);

  const now = opts?.now ?? new Date();
  if (day > now.toISOString().slice(0, 10)) return 0;
  const [year, monthOfDay, dateOfMonth] = day.split("-").map(Number);
  if (!month.values.has(monthOfDay)) return 0;

  const domMatch = dom.values.has(dateOfMonth);
  const dowMatch = dow.values.has(new Date(Date.UTC(year, monthOfDay - 1, dateOfMonth)).getUTCDay());
  const domRestricted = !dom.wildcard && !dow.wildcard;
  // cron's own rule: when both day fields are restricted, either one matching is
  // enough. With only one restricted, that one alone decides.
  if (domRestricted ? !(domMatch || dowMatch) : !(domMatch && dowMatch)) return 0;

  // Seconds, not minutes, so a start owed at 10:52:00 is not yet due at
  // 10:52:00 and is due at 10:52:30. Minute granularity calls both of those the
  // same instant and makes the alarm cry wolf once a minute on every `:52` cron.
  const cutoff =
    now.toISOString().slice(0, 10) === day
      ? now.getUTCHours() * 3600 + now.getUTCMinutes() * 60 + now.getUTCSeconds()
      : DAY_SECONDS;
  let count = 0;
  for (const h of hour.values) {
    for (const m of minute.values) {
      if (h * 3600 + m * 60 < cutoff) count += 1;
    }
  }
  return count;
}