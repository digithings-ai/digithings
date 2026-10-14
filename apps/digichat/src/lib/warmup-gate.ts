/**
 * Client warm-up gate for sleep-on-idle chat services.
 *
 * - Page load: `startWarmup()` polls /api/embed/warmup; the boot loader shows
 *   a "Waking up services…" step and only completes once every service is
 *   ready (or the budget elapses -> "error" phase, chat still revealed).
 * - Mid-session: chat requests go through `ensureWarm()`. If the last confirmed
 *   activity is older than the idle-sleep window, it re-checks warm-up first;
 *   the pending assistant row reads the phase and says "Waking up services…".
 *   The message is held (queued) and auto-sent once ready.
 * (Container env, incl. tenant config, is fixed per container boot.)
 */
import { p } from "@/lib/base-path";
import {
  getDigichatWarmupPhase,
  setDigichatWarmupPhase,
  type DigichatWarmupPhase,
} from "@digithings/ui/chat/boot-signal";

export type WarmupPhase = DigichatWarmupPhase;

/** Services sleep after ~3 min idle; re-check a bit before that. */
const IDLE_RECHECK_MS = 150_000;
const BUDGET_MS = 120_000;

let lastWarmAt = 0;
let inflight: Promise<boolean> | null = null;

async function probe(): Promise<boolean> {
  try {
    const r = await fetch(p("/api/embed/warmup"), { cache: "no-store" });
    const j = (await r.json()) as { ready?: boolean };
    return j.ready === true;
  } catch {
    return false;
  }
}

/** Poll until ready (true) or budget elapses (false). Shares one in-flight run. */
function runWarmup(showWakingAfterMs: number): Promise<boolean> {
  if (inflight) return inflight;
  inflight = (async () => {
    const t0 = Date.now();
    const show = setTimeout(() => setDigichatWarmupPhase("waking"), showWakingAfterMs);
    try {
      while (Date.now() - t0 < BUDGET_MS) {
        if (await probe()) {
          lastWarmAt = Date.now();
          setDigichatWarmupPhase("ready");
          return true;
        }
        setDigichatWarmupPhase("waking");
        await new Promise((res) => setTimeout(res, 3_000));
      }
      setDigichatWarmupPhase("error");
      return false;
    } finally {
      clearTimeout(show);
      inflight = null;
    }
  })();
  return inflight;
}

export function getWarmupPhase(): WarmupPhase {
  return getDigichatWarmupPhase();
}

/** Page load: wake every service the tenant needs. */
export function startWarmup(): Promise<boolean> {
  if (typeof window === "undefined") return Promise.resolve(true);
  return runWarmup(600);
}

/** Before a chat request: re-check if services may have gone to sleep. */
export async function ensureWarm(): Promise<void> {
  if (typeof window === "undefined") return;
  if (inflight) {
    await inflight;
  } else if (Date.now() - lastWarmAt > IDLE_RECHECK_MS) {
    await runWarmup(400);
  }
  // Even on timeout, release the request (the server retries digikey too).
}

const TRANSIENT_RE = /container|not running|disconnected|digraph unreachable|upstream_auth|service_unavailable/i;

/**
 * fetch for chat requests: waits out sleeping services first, and if the
 * request still lands on a container that is mid-restart (non-OK 5xx before
 * any stream, e.g. "Container suddenly disconnected"), re-runs warm-up and
 * resends (up to 3 tries). Non-transient errors pass through unchanged.
 */
export async function warmFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  await ensureWarm();
  let res = await fetch(input, init);
  for (let attempt = 1; attempt < 3 && !res.ok && res.status >= 500; attempt++) {
    const body = await res.clone().text().catch(() => "");
    if (!TRANSIENT_RE.test(body)) break;
    lastWarmAt = 0;
    await runWarmup(0);
    res = await fetch(input, init);
  }
  if (res.ok) lastWarmAt = Date.now();
  return res;
}

/** Call when a chat response completes so idle is measured from activity. */
export function markWarmActivity(): void {
  lastWarmAt = Date.now();
}

/** @deprecated kept for older call sites */
export const waitForWarmup = ensureWarm;
