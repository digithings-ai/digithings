/**
 * digichat license heartbeat sender.
 *
 * Started from `register()` in `src/instrumentation.ts` (guarded by
 * `NEXT_RUNTIME === "nodejs"` at the call site). Fires one attempt
 * immediately, unawaited, then every 24h (`LICENSE_HEARTBEAT_INTERVAL_MS`,
 * owner-fixed — deliberately not an env var). Every timer is `unref()`'d so
 * the scheduler never holds the process open.
 *
 * Fail-open recognition (§5.5): only an HTTP 401 carrying a recognized
 * `error` code (`license_revoked` / `unknown_license`) latches `revoked`.
 * Every other outcome — including a digikey with no heartbeat route at all
 * (404) — leaves serving untouched and schedules a bounded backoff. This is
 * what lets slice 2 ship safely before the slice-3 receiver exists.
 *
 * Secret hygiene: the raw JWT travels only in the `Authorization` header. It
 * is never logged, never put in the body, and never written to a file.
 */

import { applyHeartbeatResult, getHeartbeatContext, getLicenseState } from "./state";
import { resolveDigichatVersion } from "./version";

export const LICENSE_HEARTBEAT_INTERVAL_MS = 24 * 60 * 60 * 1000;
export const LICENSE_HEARTBEAT_TIMEOUT_MS = 10_000;
export const LICENSE_HEARTBEAT_PATH = "/v1/licenses/heartbeat";

const BACKOFF_BASE_MS = 5 * 60 * 1000;
const BACKOFF_CAP_MS = 6 * 60 * 60 * 1000;

export type HeartbeatOutcome = "valid" | "expired" | "denied" | "error";

export interface ClassifiedHeartbeat {
  outcome: HeartbeatOutcome;
  /** Set for `denied`: which recognized error code latched. */
  detail?: string;
}

/**
 * Map an HTTP outcome to a heartbeat result (§5.5). Deny requires *both*
 * the 401 status and a recognized `error` code — a bare 401 from any other
 * layer (e.g. digikey's ordinary auth middleware answering
 * `{"error":"unauthorized"}`) must not latch.
 */
export function classifyHeartbeatResponse(
  status: number,
  body: unknown,
): ClassifiedHeartbeat {
  const record =
    typeof body === "object" && body !== null
      ? (body as Record<string, unknown>)
      : {};
  if (status === 200 && record.license_status === "valid") return { outcome: "valid" };
  if (status === 200 && record.license_status === "expired") return { outcome: "expired" };
  if (status === 401 && record.error === "license_revoked") {
    return { outcome: "denied", detail: "heartbeat_deny_revoked" };
  }
  if (status === 401 && record.error === "unknown_license") {
    return { outcome: "denied", detail: "heartbeat_deny_unknown" };
  }
  return { outcome: "error" };
}

/**
 * Exponential backoff for error outcomes: 5m → 10m → 20m … capped at 6h,
 * never past 24h. `jitterRatio` is in [-0.1, 0.1]; values outside are
 * clamped so a bad caller cannot weaken the cadence.
 */
export function computeBackoffMs(
  consecutiveErrors: number,
  jitterRatio = 0,
): number {
  const n = Math.max(1, Math.floor(consecutiveErrors));
  const delay = Math.min(
    BACKOFF_BASE_MS * 2 ** (n - 1),
    BACKOFF_CAP_MS,
    LICENSE_HEARTBEAT_INTERVAL_MS,
  );
  const jitter = Math.max(-0.1, Math.min(0.1, jitterRatio));
  return Math.round(Math.min(delay * (1 + jitter), LICENSE_HEARTBEAT_INTERVAL_MS));
}

export interface HeartbeatBody {
  license_id: string;
  customer: string;
  license_status: string;
  version: string;
  hosts_configured: string[];
  started_at: string;
  seq: number;
}

export interface HeartbeatScheduler {
  setInterval: (cb: () => void, ms: number) => unknown;
  clearInterval: (handle: unknown) => void;
  setTimeout: (cb: () => void, ms: number) => unknown;
  clearTimeout: (handle: unknown) => void;
}

export interface HeartbeatDeps {
  fetchFn?: typeof fetch;
  scheduler?: HeartbeatScheduler;
  jitterRatio?: () => number;
}

interface HeartbeatRuntime {
  timer: unknown;
  retryTimer: unknown;
  inFlight: boolean;
  seq: number;
  consecutiveErrors: number;
}

const nodeScheduler: HeartbeatScheduler = {
  setInterval: (cb, ms) => setInterval(cb, ms),
  clearInterval: (handle) => clearInterval(handle as NodeJS.Timeout),
  setTimeout: (cb, ms) => setTimeout(cb, ms),
  clearTimeout: (handle) => clearTimeout(handle as NodeJS.Timeout),
};

let runtime: HeartbeatRuntime | null = null;
let runtimeScheduler: HeartbeatScheduler = nodeScheduler;
let runtimeFetch: typeof fetch | null = null;
let runtimeJitter: () => number = () => Math.random() * 0.2 - 0.1;
/** Re-entry for retry timers (set by start, cleared by stop). */
let reattempt: (() => void) | null = null;

function unref(handle: unknown): void {
  (handle as { unref?: () => void } | null)?.unref?.();
}

function digikeyBase(): string {
  return (process.env.DIGIKEY_URL ?? "").trim().replace(/\/+$/, "");
}

/** Filter `Authorization` / JWT-shaped values out of logged args (defense in depth). */
function safeLogArgs(args: unknown[]): unknown[] {
  return args.map((a) => {
    if (typeof a !== "string") return a;
    if (/^Bearer\s+/i.test(a)) return "[redacted-credential]";
    if (/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(a)) {
      return "[redacted-credential]";
    }
    return a;
  });
}

function logInfo(...args: unknown[]): void {
  console.log(...safeLogArgs(args));
}

function logWarn(...args: unknown[]): void {
  console.warn(...safeLogArgs(args));
}

export function stopLicenseHeartbeat(): void {
  if (runtime) {
    if (runtime.timer) runtimeScheduler.clearInterval(runtime.timer);
    if (runtime.retryTimer) runtimeScheduler.clearTimeout(runtime.retryTimer);
  }
  runtime = null;
  reattempt = null;
}

/**
 * Schedule the 24h sender and fire one attempt immediately, unawaited.
 * `unlicensed` containers never start a timer. Safe to call twice (second
 * call is a no-op until `stopLicenseHeartbeat()`).
 */
export function startLicenseHeartbeat(deps: HeartbeatDeps = {}): void {
  if (runtime) return;
  const ctx = getHeartbeatContext();
  if (ctx.licenseStatus === "unlicensed" || !ctx.rawJwt) return;

  runtimeScheduler = deps.scheduler ?? nodeScheduler;
  runtimeFetch = deps.fetchFn ?? globalThis.fetch.bind(globalThis);
  runtimeJitter = deps.jitterRatio ?? (() => Math.random() * 0.2 - 0.1);

  const rt: HeartbeatRuntime = {
    timer: null,
    retryTimer: null,
    inFlight: false,
    seq: 0,
    consecutiveErrors: 0,
  };
  runtime = rt;

  async function attempt(): Promise<void> {
    if (runtime !== rt || rt.inFlight) return;
    rt.inFlight = true;
    try {
      await sendOnce(rt);
    } catch (e) {
      // The attempt body never throws out of the timer callback: a crash
      // here is an ordinary error outcome with backoff.
      rt.consecutiveErrors += 1;
      const delay = scheduleRetry(rt);
      logWarn(
        `[license] heartbeat error detail=unexpected seq=${rt.seq} ` +
          `next_attempt_in_ms=${delay} error=${e instanceof Error ? e.message : String(e)}`,
      );
    } finally {
      rt.inFlight = false;
    }
  }

  reattempt = () => {
    void attempt();
  };

  rt.timer = runtimeScheduler.setInterval(() => {
    void attempt();
  }, LICENSE_HEARTBEAT_INTERVAL_MS);
  unref(rt.timer);

  // First attempt is fire-and-forget: it must not delay register()
  // returning, must not block the first request, and its failure is an
  // ordinary error.
  void attempt();
}

async function sendOnce(rt: HeartbeatRuntime): Promise<void> {
  const fetchFn = runtimeFetch;
  if (!fetchFn) return;
  const ctx = getHeartbeatContext();
  if (!ctx.rawJwt || !ctx.licenseId || !ctx.sub) return;
  rt.seq += 1;
  const seq = rt.seq;
  const snapshot = getLicenseState();
  const body: HeartbeatBody = {
    license_id: ctx.licenseId,
    customer: ctx.sub,
    license_status: snapshot.state,
    version: resolveDigichatVersion(),
    hosts_configured: ctx.hostsConfigured,
    started_at: ctx.startedAt,
    seq,
  };
  const rawJwt = ctx.rawJwt;
  const licenseId = ctx.licenseId;
  const url = `${digikeyBase()}${LICENSE_HEARTBEAT_PATH}`;
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort(), LICENSE_HEARTBEAT_TIMEOUT_MS);
  // This timeout only bounds the fetch; it must not keep the process alive.
  (timeout as unknown as { unref?: () => void }).unref?.();
  try {
    const res = await fetchFn(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${rawJwt}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    let parsed: unknown = null;
    try {
      parsed = await res.json();
    } catch {
      parsed = null;
    }
    const classified = classifyHeartbeatResponse(res.status, parsed);
    if (classified.outcome === "valid") {
      rt.consecutiveErrors = 0;
      clearRetry(rt);
      applyHeartbeatResult("valid");
      logInfo(`[license] heartbeat ok detail=valid license_id=${licenseId} seq=${seq}`);
    } else if (classified.outcome === "expired") {
      rt.consecutiveErrors = 0;
      clearRetry(rt);
      applyHeartbeatResult("expired");
      logWarn(
        `[license] status=expired detail=heartbeat_expired license_id=${licenseId} seq=${seq}`,
      );
    } else if (classified.outcome === "denied") {
      rt.consecutiveErrors = 0;
      clearRetry(rt);
      applyHeartbeatResult("denied", classified.detail);
      logWarn(
        `[license] status=revoked detail=${classified.detail} license_id=${licenseId} seq=${seq}`,
      );
    } else {
      rt.consecutiveErrors += 1;
      const problem = parsed === null ? "bad_body" : `http_${res.status}`;
      const delay = scheduleRetry(rt);
      logWarn(
        `[license] heartbeat error detail=${problem} seq=${seq} next_attempt_in_ms=${delay}`,
      );
    }
  } catch (e) {
    rt.consecutiveErrors += 1;
    const reason = e instanceof Error && e.name === "AbortError" ? "timeout" : "unreachable";
    const delay = scheduleRetry(rt);
    logWarn(
      `[license] heartbeat error detail=${reason} seq=${seq} next_attempt_in_ms=${delay}`,
    );
  } finally {
    clearTimeout(timeout);
  }
}

function clearRetry(rt: HeartbeatRuntime): void {
  if (rt.retryTimer) {
    runtimeScheduler.clearTimeout(rt.retryTimer);
    rt.retryTimer = null;
  }
}

/** Schedule the next error retry; returns the delay so callers can log the exact value. */
function scheduleRetry(rt: HeartbeatRuntime): number {
  if (runtime !== rt) return 0;
  clearRetry(rt);
  const delay = Math.min(
    computeBackoffMs(rt.consecutiveErrors, runtimeJitter()),
    LICENSE_HEARTBEAT_INTERVAL_MS,
  );
  rt.retryTimer = runtimeScheduler.setTimeout(() => {
    if (runtime === rt) rt.retryTimer = null;
    reattempt?.();
  }, delay);
  unref(rt.retryTimer);
  return delay;
}

/** Test hook — inspect scheduler state. */
export function getHeartbeatRuntimeForTests(): {
  seq: number;
  consecutiveErrors: number;
  running: boolean;
} {
  return {
    seq: runtime?.seq ?? 0,
    consecutiveErrors: runtime?.consecutiveErrors ?? 0,
    running: runtime !== null,
  };
}
