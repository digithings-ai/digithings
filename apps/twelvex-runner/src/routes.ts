/**
 * Paths the container HTTP server accepts. Cron copies these.
 *
 * The argv each route runs lives in one place only: the container entrypoint
 * (container/server.py). A second copy of it here would drift from the pinned
 * twelve-x ref without any run failing, so this module keeps no command
 * mirror.
 */
export const ROUTES = ["ingest", "heartbeat", "session"] as const;
export type Route = (typeof ROUTES)[number];

export const BUCKETS = ["intraday", "daily", "weekly", "quarterly"] as const;
export type Bucket = (typeof BUCKETS)[number];

/** FX research sessions, the label the twelve-x workflow uses for this class. */
export const SESSIONS = ["asia", "london", "new_york"] as const;
export type Session = (typeof SESSIONS)[number];

export function isRoute(value: string): value is Route {
  return (ROUTES as readonly string[]).includes(value);
}

export function isBucket(value: string): value is Bucket {
  return (BUCKETS as readonly string[]).includes(value);
}

export function isSession(value: string): value is Session {
  return (SESSIONS as readonly string[]).includes(value);
}

/**
 * A calendar date in YYYY-MM-DD form, the only shape the workflow's run_date
 * input accepts. A real date only: 2026-02-30 is not a date.
 *
 * The year starts at 1. The container parses the same value with Python's
 * date.fromisoformat, which has no year 0, so a date this module accepted
 * would come back from the container as a 400 instead of a 400 from here.
 */
export function isIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return false;
  if (parsed.getUTCFullYear() < 1) return false;
  // The date parser normalizes an overflowing day (2023-02-29 becomes
  // 2023-03-01), so the round trip is what proves the calendar date exists.
  return parsed.toISOString().slice(0, 10) === value;
}

export function defaultTimeoutSeconds(route: Route): number {
  if (route === "ingest") return 1200;
  // The FX research job allows 120 minutes in the workflow.
  if (route === "session") return 7200;
  return 300;
}
