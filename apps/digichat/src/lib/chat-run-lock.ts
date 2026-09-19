/**
 * In-memory per-session run mutex + optional run-id dedupe for POST /api/chat (#3475).
 *
 * Multi-instance digichat still relies on the client busy-gate; this stops
 * double-invoke on a single Node process (double-click regen, replayed run id).
 */

import { BoundedTTLMap } from "@/lib/bounded-map";

const ACTIVE_TTL_MS = 3 * 60_000;
const RUN_ID_TTL_MS = 10 * 60_000;
const MAX_KEYS = 4_096;

type ActiveEntry = { runId: string | null };
type RunIdEntry = { status: "in_progress" | "done" };

const activeBySession = new BoundedTTLMap<string, ActiveEntry>(MAX_KEYS, ACTIVE_TTL_MS);
const runIdsBySession = new BoundedTTLMap<string, RunIdEntry>(MAX_KEYS, RUN_ID_TTL_MS);

export type ChatRunAcquireResult =
  | { ok: true; release: () => void }
  | { ok: false; error: "run_in_progress" | "run_id_replay" };

function runIdKey(sessionKey: string, runId: string): string {
  return `${sessionKey}::${runId}`;
}

/** Test helper — clears process-local lock state between Vitest cases. */
export function resetChatRunLocksForTests(): void {
  activeBySession.clear();
  runIdsBySession.clear();
}

/**
 * Acquire an exclusive run lock for `sessionKey`.
 * Duplicate `runId` (same session) → `run_id_replay` (409); do not start a second invoke.
 * Concurrent open run → `run_in_progress` (409).
 */
export function acquireChatRunLock(
  sessionKey: string,
  runId: string | null,
): ChatRunAcquireResult {
  if (runId) {
    const prior = runIdsBySession.get(runIdKey(sessionKey, runId));
    if (prior) {
      return { ok: false, error: "run_id_replay" };
    }
  }
  if (activeBySession.get(sessionKey)) {
    return { ok: false, error: "run_in_progress" };
  }

  activeBySession.set(sessionKey, { runId });
  if (runId) {
    runIdsBySession.set(runIdKey(sessionKey, runId), { status: "in_progress" }, RUN_ID_TTL_MS);
  }

  let released = false;
  const release = () => {
    if (released) return;
    released = true;
    activeBySession.delete(sessionKey);
    if (runId) {
      runIdsBySession.set(runIdKey(sessionKey, runId), { status: "done" }, RUN_ID_TTL_MS);
    }
  };

  return { ok: true, release };
}

/** Wrap a streaming Response so the run lock releases when the body ends or aborts. */
export function releaseChatRunLockOnResponseEnd(res: Response, release: () => void): Response {
  if (!res.body) {
    release();
    return res;
  }

  const reader = res.body.getReader();
  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        const { done, value } = await reader.read();
        if (done) {
          release();
          controller.close();
          return;
        }
        controller.enqueue(value);
      } catch (err) {
        release();
        controller.error(err);
      }
    },
    cancel(reason) {
      release();
      return reader.cancel(reason);
    },
  });

  return new Response(stream, {
    status: res.status,
    statusText: res.statusText,
    headers: res.headers,
  });
}
