/** Paths the container HTTP server accepts. Cron copies these. */
export const ROUTES = ["ingest", "heartbeat"] as const;
export type Route = (typeof ROUTES)[number];

export const BUCKETS = ["intraday", "daily", "weekly", "quarterly"] as const;
export type Bucket = (typeof BUCKETS)[number];

export function isRoute(value: string): value is Route {
  return (ROUTES as readonly string[]).includes(value);
}

export function isBucket(value: string): value is Bucket {
  return (BUCKETS as readonly string[]).includes(value);
}

/** Same argv the GitHub Actions steps run. No shell. */
export function commandFor(route: Route, bucket?: string): string[] {
  if (route === "heartbeat") {
    return ["python", "-m", "twelve_x.scripts.primemarket_session_heartbeat"];
  }
  if (!bucket || !isBucket(bucket)) {
    throw new Error("ingest requires bucket intraday|daily|weekly|quarterly");
  }
  return ["python", "-m", "twelve_x.scripts.ingest_market_context", bucket];
}

export function defaultTimeoutSeconds(route: Route): number {
  return route === "ingest" ? 1200 : 300;
}
