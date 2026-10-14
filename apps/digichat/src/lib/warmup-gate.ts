/**
 * Client warm-up gate: on embed load, poll /api/embed/warmup until the chat
 * services (which sleep on idle) report ready. Chat requests sent during boot
 * wait on `waitForWarmup()` and go out automatically once ready, so a cold
 * start never surfaces as "assistant not available". Best effort: after the
 * budget elapses the request is released anyway (server retries too).
 * (Container env, incl. tenant config, is fixed per container boot.)
 */
import { p } from "@/lib/base-path";

export type WarmupPhase = "idle" | "waking" | "almost" | "ready";

let phase: WarmupPhase = "idle";
let started = false;
const listeners = new Set<(ph: WarmupPhase) => void>();
let resolveReady: () => void = () => {};
const readyPromise = new Promise<void>((r) => (resolveReady = r));

function set(ph: WarmupPhase) {
  phase = ph;
  for (const l of listeners) l(ph);
  if (ph === "ready") resolveReady();
}

export function getWarmupPhase(): WarmupPhase {
  return phase;
}

export function subscribeWarmup(l: (ph: WarmupPhase) => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function startWarmup(budgetMs = 150_000): void {
  if (started || typeof window === "undefined") return;
  started = true;
  const t0 = Date.now();
  // Only show the status line if boot is actually slow (warm stacks answer fast).
  const showTimer = setTimeout(() => phase !== "ready" && set("waking"), 1_500);
  (async () => {
    while (Date.now() - t0 < budgetMs) {
      try {
        const r = await fetch(p("/api/embed/warmup"), { cache: "no-store" });
        const j = (await r.json()) as { ready?: boolean; services?: Record<string, string> };
        if (j.ready) break;
        const s = Object.values(j.services ?? {});
        if (s.length && s.filter((v) => v === "ready").length >= Math.ceil(s.length / 2) && phase === "waking")
          set("almost");
      } catch {
        /* still waking */
      }
      if (Date.now() - t0 > 35_000 && phase === "waking") set("almost");
      await new Promise((res) => setTimeout(res, 4_000));
    }
    clearTimeout(showTimer);
    set("ready");
  })();
}

export function waitForWarmup(): Promise<void> {
  if (!started || phase === "ready") return Promise.resolve();
  return readyPromise;
}

export function warmupStatusText(ph: WarmupPhase): string | null {
  if (ph === "waking") return "Waking up chat services…";
  if (ph === "almost") return "Almost ready…";
  return null;
}
