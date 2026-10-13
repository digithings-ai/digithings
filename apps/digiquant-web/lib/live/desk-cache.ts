/**
 * One client store for the desk datasets, shared by the web desk and `clients/digiquant-tui`.
 *
 * The desk reads the same five official routes from every surface, and each surface used to
 * refetch them on mount: switching a desk page threw away the previous read and rendered the
 * unloaded state until the network answered. This cache keeps one entry per dataset so a
 * remount inside `maxAgeMs` paints from the last read instead.
 *
 * Framework-agnostic on purpose — no React, no fetch, no timers. The caller supplies the reader,
 * which is what lets both runtimes share it (the TUI already imports across trees by relative
 * path; see `components/desk/web-slots.ts` for the precedent shape).
 */

export interface DeskCacheOptions {
  /** How long a read stays fresh. `0` means every load refetches. Default 30s. */
  maxAgeMs?: number;
  /** Clock, injectable so tests are deterministic instead of timer-dependent. */
  now?: () => number;
}

export interface DeskCache<T> {
  /** The cached value for `key` if it is still fresh, else `undefined`. */
  peek: (key: string) => T | undefined;
  /** Store a value directly, as if it had just been read. */
  set: (key: string, value: T) => void;
  /** Drop one key, or every key when called with no argument. */
  invalidate: (key?: string) => void;
  /** How many keys are currently cached, fresh or not. */
  size: () => number;
  /**
   * The value for `key`, reading it through `fetcher` only when there is no fresh entry.
   * Concurrent calls for the same key share one read.
   */
  load: (key: string, fetcher: () => Promise<T>) => Promise<T>;
}

const DEFAULT_MAX_AGE_MS = 30_000;

/** A keyed store with a freshness window and in-flight read deduplication. */
export function createDeskCache<T>(options: DeskCacheOptions = {}): DeskCache<T> {
  const maxAgeMs = options.maxAgeMs ?? DEFAULT_MAX_AGE_MS;
  const now = options.now ?? (() => Date.now());
  const values = new Map<string, { value: T; at: number }>();
  const inflight = new Map<string, Promise<T>>();

  const isFresh = (at: number): boolean => maxAgeMs > 0 && now() - at < maxAgeMs;

  return {
    peek: (key) => {
      const hit = values.get(key);
      return hit && isFresh(hit.at) ? hit.value : undefined;
    },
    set: (key, value) => {
      values.set(key, { value, at: now() });
    },
    invalidate: (key) => {
      if (key === undefined) {
        values.clear();
        inflight.clear();
        return;
      }
      values.delete(key);
      inflight.delete(key);
    },
    size: () => values.size,
    load: (key, fetcher) => {
      const hit = values.get(key);
      if (hit && isFresh(hit.at)) return Promise.resolve(hit.value);
      const running = inflight.get(key);
      if (running) return running;
      const started = fetcher().then(
        (value) => {
          values.set(key, { value, at: now() });
          inflight.delete(key);
          return value;
        },
        (error: unknown) => {
          // A failed read is not a dataset. Drop it so the next mount retries rather than
          // serving a remembered failure until the window closes.
          inflight.delete(key);
          throw error;
        },
      );
      inflight.set(key, started);
      return started;
    },
  };
}
