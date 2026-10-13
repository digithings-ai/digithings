/**
 * Routing and auth for POST /run/{ingest|heartbeat}.
 * The container binding is injected so tests do not start an image.
 */
import { decideAlert, executeAlert, labelFor, loadOpen, verdictLine, SESSION_LABEL } from "./alerts";
import type { Env } from "./env";
import { defaultTimeoutSeconds, isBucket, isRoute, type Route } from "./routes";

export type RunBody = {
  job_id?: string;
  bucket?: string;
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
};

function authorized(request: Request, env: Env): boolean {
  const token = env.RUNNER_AUTH_TOKEN;
  if (!token) return false;
  return (request.headers.get("Authorization") ?? "") === `Bearer ${token}`;
}

function logLine(fields: Record<string, unknown>): void {
  console.log(JSON.stringify(fields));
}

export async function handle(
  request: Request,
  env: Env,
  container: Fetcher,
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

  const dryRun = env.DRY_RUN === "1" || parsed.dry_run === true;
  const body: RunBody = {
    job_id: typeof parsed.job_id === "string" ? parsed.job_id : route,
    bucket: parsed.bucket,
    timeout_seconds:
      typeof parsed.timeout_seconds === "number"
        ? parsed.timeout_seconds
        : defaultTimeoutSeconds(route),
    dry_run: dryRun,
  };
  const started = Date.now();
  logLine({ job: body.job_id, route, event: "start", dry_run: dryRun });

  const res = await container.fetch(
    new Request(`https://twelvex-runner/run/${route}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
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
  const alert = dryRun ? "none" : await publishAlert(env, route, result, body, fetchImpl, started);
  logLine({
    job: body.job_id,
    route,
    event: "exit",
    exit_code: result.exit_code,
    duration_ms: duration,
    alert,
    dry_run: dryRun,
  });
  return Response.json({ ...result, duration_ms: duration, alert, dry_run: dryRun });
}

async function publishAlert(
  env: Env,
  route: Route,
  result: RunResult,
  body: RunBody,
  fetchImpl: typeof fetch,
  now: number,
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
      reason: route === "ingest" ? verdictLine(result.log_tail ?? "") : "session probe failed",
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
