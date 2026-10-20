/**
 * Routing and auth for POST /run/{ingest|heartbeat}.
 * The container binding is injected so tests do not start an image.
 *
 * The reason a run failed is computed once, from the container log tail, and
 * travels with the exit: in the Worker log line, in the response body and in
 * the GitHub alert. A reason that stays inside the container is a reason the
 * run watch cannot read.
 */
import {
  durableObjectUnavailableResponse,
  DURABLE_OBJECT_UNAVAILABLE,
  DurableObjectUnavailableError,
  fetchDurableObject,
} from "@digithings/durable-object-reconnect";
import {
  decideAlert,
  executeAlert,
  labelFor,
  lastMeaningfulLine,
  loadOpen,
  verdictLine,
  SESSION_LABEL,
} from "./alerts";
import type { Env } from "./env";
import {
  defaultTimeoutSeconds,
  isBucket,
  isIsoDate,
  isRoute,
  isSession,
  type Route,
} from "./routes";

export type RunBody = {
  job_id?: string;
  bucket?: string;
  session?: string;
  run_date?: string;
  timeout_seconds?: number;
  dry_run?: boolean;
};

export type RunResult = {
  ok: boolean;
  exit_code: number;
  duration_ms: number;
  log_tail: string;
  dry_run: boolean;
  command: string[];
  alert: string;
  /** The one-line reason, present on a failed run. */
  reason?: string | null;
};

/**
 * The one-line reason a run failed, per route. The ingest prints a verdict
 * token, the FX graph prints no token, and the heartbeat probe has one
 * fixed meaning.
 */
export function reasonFor(route: Route, logTail: string): string {
  if (route === "ingest") return verdictLine(logTail);
  if (route === "session") return lastMeaningfulLine(logTail);
  return "session probe failed";
}

function authorized(request: Request, env: Env): boolean {
  const token = env.RUNNER_AUTH_TOKEN;
  if (!token) return false;
  return (request.headers.get("Authorization") ?? "") === `Bearer ${token}`;
}

/**
 * The workflow's run_date input: optional, a calendar date, empty means the
 * forward path. A missing value or a JSON null is absent, the same as the
 * workflow's empty default; a returned null means malformed.
 */
function readRunDate(value: unknown): string | undefined | null {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (trimmed === "") return undefined;
  return isIsoDate(trimmed) ? trimmed : null;
}

function logLine(fields: Record<string, unknown>): void {
  console.log(JSON.stringify(fields));
}

/**
 * `connectContainer` resolves the stub of the Durable Object that owns the
 * container. It is a factory, not a stub, because a reconnect must address the
 * live instance: the platform closes the instance when it recycles it, and the
 * next call has to reach the instance that took over the name.
 */
export async function handle(
  request: Request,
  env: Env,
  connectContainer: () => Fetcher,
  fetchImpl: typeof fetch = fetch,
): Promise<Response> {
  const url = new URL(request.url);
  const path =
    url.pathname.length > 1 && url.pathname.endsWith("/")
      ? url.pathname.slice(0, -1)
      : url.pathname;

  if (request.method === "GET" && path === "/healthz") {
    return Response.json({ ok: true });
  }

  const match = /^\/run\/([^/]+)$/.exec(path);
  if (request.method !== "POST" || !match || !isRoute(match[1])) {
    return new Response("Not Found", { status: 404 });
  }
  if (!authorized(request, env)) {
    return new Response("Unauthorized", { status: 401 });
  }

  const route: Route = match[1];
  let parsed: RunBody = {};
  const raw = await request.text();
  if (raw) {
    try {
      parsed = JSON.parse(raw) as RunBody;
    } catch {
      return Response.json({ error: "invalid_json" }, { status: 400 });
    }
  }
  if (route === "ingest" && (typeof parsed.bucket !== "string" || !isBucket(parsed.bucket))) {
    return Response.json({ error: "invalid_bucket" }, { status: 400 });
  }
  if (route === "session" && (typeof parsed.session !== "string" || !isSession(parsed.session))) {
    return Response.json({ error: "invalid_session" }, { status: 400 });
  }
  const runDate = readRunDate(parsed.run_date);
  if (runDate === null) {
    return Response.json({ error: "invalid_run_date" }, { status: 400 });
  }

  const dryRun = env.DRY_RUN === "1" || parsed.dry_run === true;
  const body: RunBody = {
    job_id: typeof parsed.job_id === "string" ? parsed.job_id : route,
    bucket: parsed.bucket,
    session: parsed.session,
    // Only the session route runs the graph, and only the graph reads a
    // backfill date. The other routes ignore it.
    run_date: route === "session" ? runDate : undefined,
    timeout_seconds:
      typeof parsed.timeout_seconds === "number"
        ? parsed.timeout_seconds
        : defaultTimeoutSeconds(route),
    dry_run: dryRun,
  };
  const started = Date.now();
  logLine({ job: body.job_id, route, event: "start", dry_run: dryRun });

  /**
   * The hop to the container is the hop that fails: when the platform closes
   * the Durable Object instance while the request is in flight, the connection
   * is closed and the request never reaches the container. The platform's own
   * message says to reconnect and retry, so we reconnect once; when even the
   * reconnect fails we answer 503 + Retry-After, so the caller backs off
   * instead of hammering a runner that is still coming up (run-watch
   * DIG-4753).
   */
  let res: Response;
  try {
    res = await fetchDurableObject(
      connectContainer,
      () =>
        new Request(`https://twelvex-runner/run/${route}`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        }),
    );
  } catch (error) {
    if (error instanceof DurableObjectUnavailableError) {
      logLine({
        job: body.job_id,
        route,
        event: "exit",
        exit_code: null,
        error: DURABLE_OBJECT_UNAVAILABLE,
      });
      return durableObjectUnavailableResponse(
        "the runner's Durable Object instance was not available; retry later",
      );
    }
    throw error;
  }
  const text = await res.text();
  if (res.status === 409) {
    logLine({ job: body.job_id, route, event: "exit", exit_code: null, error: "busy" });
    return Response.json({ error: "busy" }, { status: 409 });
  }
  if (!res.ok) {
    logLine({
      job: body.job_id,
      route,
      event: "exit",
      exit_code: null,
      error: `container_http_${res.status}`,
    });
    return Response.json({ error: "container_failed" }, { status: 502 });
  }

  let result: RunResult;
  try {
    result = JSON.parse(text) as RunResult;
  } catch {
    return Response.json({ error: "container_bad_json" }, { status: 502 });
  }
  const duration = result.duration_ms || Date.now() - started;
  // The reason is read off the tail here, once, so the log line, the
  // response and the alert all carry the same words.
  const reason = result.exit_code === 0 ? null : reasonFor(route, result.log_tail ?? "");
  const alert = dryRun
    ? "none"
    : await publishAlert(env, route, result, body, fetchImpl, started, reason);
  logLine({
    job: body.job_id,
    route,
    event: "exit",
    exit_code: result.exit_code,
    duration_ms: duration,
    reason,
    alert,
    dry_run: dryRun,
  });
  return Response.json({ ...result, duration_ms: duration, reason, alert, dry_run: dryRun });
}

async function publishAlert(
  env: Env,
  route: Route,
  result: RunResult,
  body: RunBody,
  fetchImpl: typeof fetch,
  now: number,
  reason: string | null,
): Promise<string> {
  const failureLabel = labelFor(route, result.exit_code);
  const closing = route === "heartbeat" && result.exit_code === 0;
  if (!failureLabel && !closing) return "none";
  const token = env.GH_ISSUES_TOKEN;
  if (!token) {
    logLine({ job: body.job_id, route, alert: "unconfigured" });
    return "unconfigured";
  }
  const lookupLabel = closing ? SESSION_LABEL : failureLabel;
  if (!lookupLabel) return "none";
  try {
    const open = await loadOpen(token, lookupLabel, fetchImpl, now);
    const decision = decideAlert({
      route,
      exitCode: result.exit_code,
      bucket: body.bucket,
      session: body.session,
      reason: reason ?? "the run failed",
      logTail: result.log_tail,
      now,
      open,
    });
    await executeAlert(token, decision, fetchImpl);
    return decision.action;
  } catch (err) {
    logLine({
      job: body.job_id,
      route,
      alert: "error",
      error: err instanceof Error ? err.message : "alert_failed",
    });
    return "error";
  }
}
