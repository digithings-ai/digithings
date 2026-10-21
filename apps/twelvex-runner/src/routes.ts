/** Paths the container HTTP server accepts. Cron copies these. */
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

/** Same argv the GitHub Actions steps run. No shell. */
export function commandFor(route: Route, bucket?: string, session?: string): string[] {
  if (route === "heartbeat") {
    return ["python", "-m", "twelve_x.scripts.primarketet_session_heartbeat"];
  }
  if (route === "session") {
    // The graph is the step that decides the exit code. The calendar ingest
    // runs first and is not fatal, exactly like the workflow step that
    // carries continue-on-error.
    if (!session || !isSession(session)) {
      throw new Error("session requires session asia|london|new_york");
    }
    return ["python", "-m", "twelve_x.graph"];
  }
  if (!bucket || !isBucket(bucket)) {
    throw new Error("ingest requires bucket intraday|daily|weekly|quarterly");
  }
  return ["python", "-m", "twelve_x.scripts.ingest_market_context", bucket];
}

export function defaultTimeoutSeconds(route: Route): number {
  if (route === "ingest") return 1200;
  // The FX research job allows 120 minutes in the workflow.
  if (route === "session") return 7200;
  return 300;
}
