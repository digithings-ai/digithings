/**
 * America/New_York wall-clock gate for at-open jobs.
 * Admit only when New York local time is ≥ 09:30 (EST or EDT).
 */

const ET = "America/New_York";

function etParts(when: Date): { hour: number; minute: number } {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: ET,
    hour: "numeric",
    minute: "numeric",
    hourCycle: "h23",
  });
  const parts = fmt.formatToParts(when);
  const hour = Number(parts.find((p) => p.type === "hour")?.value ?? "0");
  const minute = Number(parts.find((p) => p.type === "minute")?.value ?? "0");
  return { hour, minute };
}

/** True when America/New_York wall clock is at or after 09:30. */
export function isAtOrAfterEtOpen(when: Date | number): boolean {
  const d = typeof when === "number" ? new Date(when) : when;
  const { hour, minute } = etParts(d);
  return hour > 9 || (hour === 9 && minute >= 30);
}
