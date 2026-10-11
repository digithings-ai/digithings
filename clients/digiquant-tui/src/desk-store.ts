/**
 * The desk data store: one framework-agnostic cache that the digiquant web desk
 * and this TUI both read through.
 *
 * Every desk dataset is one API route, so a route is the cache key. Blocks that
 * share a route (`/allocations/enriched` backs three of them) therefore share one
 * read, which is what makes "one network fetch per dataset per refresh interval"
 * true rather than aspirational.
 *
 * Three rules the desk depends on:
 *  - a read that is already in flight is never started twice;
 *  - a value that is already cached is served without touching the network;
 *  - a read that fails leaves the last good value in place, so a flaky API shows
 *    stale numbers rather than a blank panel.
 *
 * Nothing here imports React, a router or a fetch implementation. The reader is
 * injected (`fetchDataset`) and so is the clock and the timers, so the whole
 * module runs in a plain Node test without a browser.
 */

export type DeskStoreEntry<T> = { readonly value: T; readonly fetchedAt: number };
export type DeskStoreState<T> = Readonly<Record<string, DeskStoreEntry<T>>>;
export type DeskStoreFetcher<T> = (route: string, signal: AbortSignal) => Promise<T>;
export type DeskStoreListener<T> = (state: DeskStoreState<T>) => void;

/** Injected so a test can drive the refresh clock without real time passing. */
export type DeskStoreTimers = {
  setTimeout: (run: () => void, ms: number) => unknown;
  clearTimeout: (handle: unknown) => void;
};

export type DeskStoreOptions<T> = {
  fetchDataset: DeskStoreFetcher<T>;
  /** Background refresh period. `0` or less disables the refresh loop. */
  refreshMs: number;
  now?: () => number;
  timers?: Partial<DeskStoreTimers>;
};

export type DeskStore<T> = {
  readonly refreshMs: number;
  get(route: string): T | undefined;
  snapshot(): DeskStoreState<T>;
  subscribe(listener: DeskStoreListener<T>): () => void;
  /** Fetch anything not cached yet. A cached route costs no network. */
  load(routes: readonly string[]): void;
  /** Re-read every route this store has been asked about. */
  refresh(): void;
  /** `load` plus the background refresh loop. */
  preload(routes: readonly string[]): void;
  stop(): void;
  isLoading(route: string): boolean;
};

const DEFAULT_TIMERS: DeskStoreTimers = {
  setTimeout: (run, ms) => setTimeout(run, ms),
  clearTimeout: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

/** A read in flight. `dropped` marks a read whose result must be discarded. */
type Slot = { dropped: boolean; controller: AbortController };

export function createDeskStore<T>(options: DeskStoreOptions<T>): DeskStore<T> {
  const now = options.now ?? (() => Date.now());
  const timers: DeskStoreTimers = { ...DEFAULT_TIMERS, ...options.timers };
  const refreshMs = options.refreshMs;

  const listeners = new Set<DeskStoreListener<T>>();
  const open = new Map<string, Slot>();
  const known = new Set<string>();
  let state: DeskStoreState<T> = {};
  let timer: unknown = null;

  function notify(): void {
    for (const listener of [...listeners]) listener(state);
  }

  function set(route: string, value: T): void {
    state = { ...state, [route]: { value, fetchedAt: now() } };
    notify();
  }

  function run(route: string): void {
    if (open.has(route)) return;
    const slot: Slot = { dropped: false, controller: new AbortController() };
    open.set(route, slot);
    void Promise.resolve()
      .then(() => options.fetchDataset(route, slot.controller.signal))
      .then((value) => {
        if (slot.dropped) return;
        set(route, value);
      })
      .catch(() => {
        // A read that failed leaves the last good value in place: a desk that
        // loses its numbers on one bad response is worse than a stale desk.
      })
      .finally(() => {
        if (open.get(route) === slot) open.delete(route);
      });
  }

  function arm(): void {
    if (timer !== null) {
      timers.clearTimeout(timer);
      timer = null;
    }
    if (refreshMs <= 0) return;
    // A chained timeout rather than setInterval: a slow read can never stack
    // refreshes on top of each other.
    timer = timers.setTimeout(() => {
      timer = null;
      refresh();
      arm();
    }, refreshMs);
  }

  function load(routes: readonly string[]): void {
    for (const route of routes) {
      known.add(route);
      if (state[route] !== undefined) continue;
      run(route);
    }
  }

  function refresh(): void {
    for (const route of known) run(route);
  }

  function preload(routes: readonly string[]): void {
    load(routes);
    arm();
  }

  function stop(): void {
    if (timer !== null) {
      timers.clearTimeout(timer);
      timer = null;
    }
    for (const slot of open.values()) {
      slot.dropped = true;
      slot.controller.abort();
    }
    open.clear();
  }

  return {
    refreshMs,
    get: (route) => state[route]?.value,
    snapshot: () => state,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    load,
    refresh,
    preload,
    stop,
    isLoading: (route) => open.has(route),
  };
}

/**
 * Every distinct route in a block catalog, in catalog order.
 *
 * Blocks share routes, so this is the list the desk actually preloads: passing
 * `Object.values(BLOCKS).map(b => b.route)` would ask for the same read twice and
 * rely on the store to swallow the duplicate.
 */
export function uniqueRoutes<T extends { route: string }>(
  blocks: Record<string, T> | readonly T[],
): string[] {
  const list = Array.isArray(blocks) ? blocks : Object.values(blocks as Record<string, T>);
  const seen = new Set<string>();
  const routes: string[] = [];
  for (const block of list) {
    if (seen.has(block.route)) continue;
    seen.add(block.route);
    routes.push(block.route);
  }
  return routes;
}

/** Route to block kind, for a reader that needs the kind and not the block id. */
export function kindsByRoute<T extends { route: string; kind: string }>(
  blocks: Record<string, T> | readonly T[],
): Map<string, string> {
  const list = Array.isArray(blocks) ? blocks : Object.values(blocks as Record<string, T>);
  const kinds = new Map<string, string>();
  for (const block of list) if (!kinds.has(block.route)) kinds.set(block.route, block.kind);
  return kinds;
}
