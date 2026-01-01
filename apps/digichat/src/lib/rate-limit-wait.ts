/**
 * The #6110 wait the chat already shows while a turn is held.
 *
 * One `data-connection` part, same id on every write, `warming_up` while we
 * wait and `ready` when the wait ends. The loading row keeps its animation
 * and shows the message. Token-budget pauses use this waiter rather than a
 * second timer.
 */

export function abortableSleep(ms: number, signal?: AbortSignal): Promise<void> {
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve) => {
    if (signal?.aborted) {
      resolve();
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      resolve();
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

export type RateLimitWaitOptions = {
  /** Part id. The Foundry capacity retry keeps `foundry-capacity`. */
  id?: string;
  /** Stable line. Omit it and the waiter counts down in seconds (#6110). */
  message?: string;
  now?: () => number;
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>;
};

const COUNTDOWN_STEP_MS = 5_000;

/**
 * Holds the turn and tells the client. The last write clears the line
 * (`state: ready`), including when the wait is aborted.
 */
export async function waitOutRateLimit(
  writer: { write(part: unknown): void },
  delayMs: number,
  attempt: number,
  maxAttempts: number,
  signal?: AbortSignal,
  options?: RateLimitWaitOptions,
): Promise<void> {
  const id = options?.id ?? "foundry-capacity";
  const now = options?.now ?? Date.now;
  const sleep = options?.sleep ?? abortableSleep;
  const until = now() + delayMs;
  for (;;) {
    const remaining = until - now();
    if (remaining <= 0 || signal?.aborted) break;
    const message =
      options?.message ??
      `Hit the model's per-minute token limit — resuming in ${Math.max(1, Math.ceil(remaining / 1000))}s` +
        (maxAttempts > 1 ? ` (retry ${attempt} of ${maxAttempts})` : "");
    writer.write({
      type: "data-connection",
      id,
      data: { state: "warming_up", message },
    });
    await sleep(Math.min(remaining, COUNTDOWN_STEP_MS), signal);
  }
  writer.write({ type: "data-connection", id, data: { state: "ready" } });
}
