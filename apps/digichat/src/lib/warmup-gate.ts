/**
 * Client warm-up gate for sleep-on-idle chat services.
 *
 * Every chat (landing pop-up, /chat, tenant embeds) uses this gate. Page load
 * polls /api/embed/warmup. A send made while services are still waking waits
 * here and goes out once they answer, instead of failing the turn.
 */
import { p } from "@/lib/base-path";
import {
  getDigichatWarmupPhase,
  setDigichatWarmupPhase,
  signalDigichatBootStep,
} from "@digithings/ui/chat/boot-signal";

/** Services sleep after ~3 min idle; re-check a bit before that. */
const IDLE_RECHECK_MS = 150_000;
/**
 * How long a caller waits before giving up on the loader (the chat is then
 * revealed with the "slow to respond" status). Polling does NOT stop there:
 * it carries on in the background until the services answer ready.
 */
const BUDGET_MS = 120_000;
/**
 * One probe may not hold the gate longer than this. The warm-up route pings
 * auth then assistant with 25s timeouts each, so a probe that started while
 * the stack was booting could take ~50s and still answer "waking" after the
 * boot finished; the loader then sat on that stale answer while a refresh
 * (a fresh probe) loaded the chat at once (t1711u). The server keeps waking
 * the services after the client stops listening.
 */
const PROBE_TIMEOUT_MS = 10_000;
/** Backoff between probes: 1s, 1.5s, 2.25s, ... capped at 5s. */
const BACKOFF_START_MS = 1_000;
const BACKOFF_MAX_MS = 5_000;
const BACKOFF_FACTOR = 1.5;

let lastWarmAt = 0;
let polling: Promise<true> | null = null;
let serviceNames: string[] = ["auth", "assistant"];

export function getWarmupServiceNames(): readonly string[] {
  return serviceNames;
}

async function probe(): Promise<boolean> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), PROBE_TIMEOUT_MS);
  try {
    const r = await fetch(p("/api/embed/warmup"), { cache: "no-store", signal: ctrl.signal });
    const j = (await r.json()) as { ready?: boolean; services?: Record<string, string> };
    if (j.services && Object.keys(j.services).length) {
      serviceNames = Object.keys(j.services);
    }
    return j.ready === true;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

/** Probe with backoff until the services answer ready. Shares one loop. */
function pollUntilReady(): Promise<true> {
  if (polling) return polling;
  polling = (async () => {
    let wait = BACKOFF_START_MS;
    try {
      for (;;) {
        if (await probe()) {
          lastWarmAt = Date.now();
          signalDigichatBootStep("services");
          setDigichatWarmupPhase("ready");
          return true as const;
        }
        // Past a caller's budget the status stays "slow to respond" until ready.
        if (getDigichatWarmupPhase() !== "error") setDigichatWarmupPhase("waking");
        await new Promise((res) => setTimeout(res, wait));
        wait = Math.min(BACKOFF_MAX_MS, Math.round(wait * BACKOFF_FACTOR));
      }
    } finally {
      polling = null;
    }
  })();
  return polling;
}

/**
 * Resolves true the moment the services answer ready, or false once this
 * caller's budget elapses (polling continues in the background either way).
 */
function runWarmup(showWakingAfterMs: number): Promise<boolean> {
  let budget: ReturnType<typeof setTimeout> | undefined;
  const ready = pollUntilReady();
  const show = setTimeout(() => setDigichatWarmupPhase("waking"), showWakingAfterMs);
  const timedOut = new Promise<false>((res) => {
    budget = setTimeout(() => {
      signalDigichatBootStep("services");
      setDigichatWarmupPhase("error");
      res(false);
    }, BUDGET_MS);
  });
  return Promise.race([ready, timedOut]).finally(() => {
    clearTimeout(show);
    clearTimeout(budget);
  });
}

/** Page load: wake every service the tenant needs. */
export function startWarmup(): Promise<boolean> {
  if (typeof window === "undefined") return Promise.resolve(true);
  return runWarmup(600);
}

/** Before a chat request: re-check if services may have gone to sleep. */
export async function ensureWarm(): Promise<void> {
  if (typeof window === "undefined") return;
  if (polling || Date.now() - lastWarmAt > IDLE_RECHECK_MS) {
    await runWarmup(400);
  }
}

const TRANSIENT_RE = /container|not running|disconnected|digraph unreachable|upstream_auth|upstream_unavailable|service_unavailable/i;

/**
 * fetch for chat requests: waits out sleeping services first, and if the
 * request still lands on a container that is mid-restart, re-runs warm-up
 * and resends (up to 3 tries). Non-transient errors pass through unchanged.
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
