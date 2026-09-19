/**
 * America/New_York wall-clock gate for at-open jobs.
 * Admit only the season-correct clock when New York local time is ≥ 09:30.
 */

const ET = "America/New_York";
export const AT_OPEN_EDT_CRON = "40 13 * * MON-FRI";
export const AT_OPEN_EST_CRON = "40 14 * * MON-FRI";

function etParts(when: Date): { hour: number; minute: number; offsetHours: number } {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: ET,
    hour: "numeric",
    minute: "numeric",
    hourCycle: "h23",
    timeZoneName: "shortOffset",
  });
  const parts = fmt.formatToParts(when);
  const hour = Number(parts.find((p) => p.type === "hour")?.value ?? "0");
  const minute = Number(parts.find((p) => p.type === "minute")?.value ?? "0");
  const offset = parts.find((p) => p.type === "timeZoneName")?.value ?? "";
  const match = /^GMT([+-]\d{1,2})$/.exec(offset);
  if (!match) throw new Error(`unexpected ${ET} offset: ${offset}`);
  const offsetHours = Number(match[1]);
  if (offsetHours !== -4 && offsetHours !== -5) {
    throw new Error(`unexpected ${ET} offset hours: ${offsetHours}`);
  }
  return { hour, minute, offsetHours };
}

/** True when America/New_York wall clock is at or after 09:30. */
export function isAtOrAfterEtOpen(when: Date | number): boolean {
  const d = typeof when === "number" ? new Date(when) : when;
  const { hour, minute } = etParts(d);
  return hour > 9 || (hour === 9 && minute >= 30);
}

/** True only for the EDT/EST cron that belongs to the scheduled date. */
export function shouldDispatchAtOpen(cron: string, when: Date | number): boolean {
  const d = typeof when === "number" ? new Date(when) : when;
  const { offsetHours } = etParts(d);
  const expected = offsetHours === -4 ? AT_OPEN_EDT_CRON : AT_OPEN_EST_CRON;
  return cron === expected && isAtOrAfterEtOpen(d);
}
