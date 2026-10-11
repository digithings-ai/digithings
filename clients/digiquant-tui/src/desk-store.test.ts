/**
 * The store's contract, pinned. Every read here goes through the injected clock
 * and the injected timers, so the suite proves the refresh period and the dedupe
 * without waiting on real time.
 */
import { describe, expect, it } from "bun:test";

import { createDeskStore, kindsByRoute, uniqueRoutes } from "./desk-store";

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
};

/**
 * One real macrotask drains the whole microtask queue, so a read that has been
 * started has finished its `then`/`catch`/`finally` chain by the time this
 * resolves. Four `await Promise.resolve()` turns were not enough.
 */
const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** A clock the test drives. `advance` fires every timer that came due, in order. */
function testClock() {
  let time = 1_000;
  let seq = 0;
  const due: { at: number; id: number; run: () => void }[] = [];
  return {
    timers: {
      setTimeout: (run: () => void, ms: number) => {
        const id = ++seq;
        due.push({ at: time + ms, id, run });
        return id;
      },
      clearTimeout: (handle: unknown) => {
        const index = due.findIndex((entry) => entry.id === handle);
        if (index >= 0) due.splice(index, 1);
      },
    },
    now: () => time,
    advance(ms: number) {
      time += ms;
      for (;;) {
        const ready = due.filter((entry) => entry.at <= time).sort((a, b) => a.at - b.at || a.id - b.id);
        const next = ready[0];
        if (!next) return;
        due.splice(due.indexOf(next), 1);
        next.run();
      }
    },
    armed: () => due.length,
  };
}

/** A store whose reads stay pending until the test settles them by hand. */
function controllableStore(refreshMs = 30_000) {
  const clock = testClock();
  const calls: string[] = [];
  const aborted: string[] = [];
  const reads = new Map<string, Deferred<string>>();
  const store = createDeskStore<string>({
    refreshMs,
    now: clock.now,
    timers: clock.timers,
    fetchDataset: (route, signal) => {
      calls.push(route);
      const gate = deferred<string>();
      reads.set(route, gate);
      signal.addEventListener("abort", () => aborted.push(route));
      return gate.promise;
    },
  });
  const settle = async (route: string, value: string) => {
    for (let turn = 0; turn < 10 && !reads.has(route); turn += 1) await flush();
    const gate = reads.get(route);
    if (!gate) throw new Error(`no read was opened for ${route}`);
    // Consume the gate. A refresh opens a NEW one under the same key, and
    // settling that round against the previous round's resolved promise would
    // be a no-op that reads as "the interval never ran".
    reads.delete(route);
    gate.resolve(value);
    await flush();
  };
  return { store, clock, calls, aborted, settle, flush };
}

const ROUTES = ["/brief", "/portfolio", "/performance"] as const;

describe("desk store preload", () => {
  it("reads every dataset it is given", async () => {
    const { store, calls, settle } = controllableStore(0);
    store.preload([...ROUTES]);
    await flush();
    expect([...calls].sort()).toEqual([...ROUTES].sort());
    await settle("/brief", "b");
    expect(store.get("/brief")).toBe("b");
  });

  it("caches a dataset, so a page switch costs no network", async () => {
    const { store, calls, settle } = controllableStore(0);
    store.load(["/brief"]);
    await settle("/brief", "first");

    // The switch back to a page whose dataset is already cached.
    store.load(["/brief"]);
    store.load(["/brief"]);
    await flush();

    expect(calls).toEqual(["/brief"]);
    expect(store.get("/brief")).toBe("first");
  });

  it("still fetches a route it has never read", async () => {
    const { store, calls, settle } = controllableStore(0);
    store.load(["/brief"]);
    await settle("/brief", "first");
    store.load(["/portfolio"]);
    await flush();

    expect(calls).toEqual(["/brief", "/portfolio"]);
    // Nothing is served before the read lands: no invented value, no empty string.
    expect(store.get("/portfolio")).toBeUndefined();
    await settle("/portfolio", "p");
    expect(store.get("/portfolio")).toBe("p");
  });
});

describe("desk store dedupe", () => {
  it("runs one read per dataset however many callers ask", async () => {
    const { store, calls, settle } = controllableStore(0);
    // Two page loads, a preload and a manual refresh all land while the read is
    // still open.
    store.load(["/brief"]);
    store.load(["/brief"]);
    store.preload(["/brief"]);
    store.refresh();
    await flush();

    expect(calls).toEqual(["/brief"]);
    await settle("/brief", "b");
    expect(store.get("/brief")).toBe("b");
  });

  it("shares one read between blocks on the same route", async () => {
    const { store, calls, settle } = controllableStore(0);
    store.preload(["/allocations/enriched"]);
    await settle("/allocations/enriched", "a");
    store.load(["/allocations/enriched"]);
    await flush();

    expect(calls).toEqual(["/allocations/enriched"]);
  });
});

describe("desk store refresh", () => {
  it("costs exactly one read per dataset per interval", async () => {
    const { store, calls, clock, settle } = controllableStore(30_000);
    store.preload([...ROUTES]);
    await Promise.all(ROUTES.map((route) => settle(route, `${route}@1`)));
    const afterPreload = calls.length;

    clock.advance(29_999);
    await flush();
    expect(calls.length).toBe(afterPreload);

    clock.advance(1);
    await Promise.all(ROUTES.map((route) => settle(route, `${route}@2`)));
    expect(calls.length).toBe(afterPreload + ROUTES.length);

    // A second full period buys exactly one more round, not two.
    clock.advance(30_000);
    await Promise.all(ROUTES.map((route) => settle(route, `${route}@3`)));
    expect(calls.length).toBe(afterPreload + ROUTES.length * 2);
  });

  it("does not add a read when a refresh lands on a dataset already in flight", async () => {
    const { store, calls, clock, settle } = controllableStore(30_000);
    store.preload(["/brief"]);
    await settle("/brief", "one");
    calls.length = 0;

    clock.advance(30_000); // the interval opens a read
    await flush();
    store.refresh(); // a page switch asks again while that read is open
    store.load(["/brief"]);
    await flush();

    expect(calls).toEqual(["/brief"]);
    await settle("/brief", "two");
    expect(store.get("/brief")).toBe("two");
  });

  it("runs no interval at all when the period is not positive", () => {
    const { store, clock } = controllableStore(0);
    store.preload(["/brief"]);
    expect(clock.armed()).toBe(0);
    store.stop();
  });

  it("reports which dataset is still loading", async () => {
    const { store, settle, flush } = controllableStore(0);
    store.load(["/brief"]);
    await flush();
    expect(store.isLoading("/brief")).toBe(true);
    await settle("/brief", "b");
    expect(store.isLoading("/brief")).toBe(false);
  });
});

describe("desk store subscribers", () => {
  it("tells a subscriber once per settled dataset", async () => {
    const { store, settle } = controllableStore(0);
    const seen: string[][] = [];
    store.subscribe((state) => seen.push(Object.keys(state)));
    store.load(["/brief"]);
    await settle("/brief", "b");

    expect(seen).toEqual([["/brief"]]);
  });

  it("stops telling a subscriber once it unsubscribes", async () => {
    const { store, settle } = controllableStore(0);
    let calls = 0;
    const off = store.subscribe(() => {
      calls += 1;
    });
    store.load(["/brief"]);
    await settle("/brief", "b");
    off();
    store.refresh();
    await settle("/brief", "c");

    expect(calls).toBe(1);
  });

  it("keeps the snapshot reference stable until something changes", async () => {
    const { store, settle } = controllableStore(0);
    const before = store.snapshot();
    expect(store.snapshot()).toBe(before);
    store.load(["/brief"]);
    await settle("/brief", "b");
    expect(store.snapshot()).not.toBe(before);
  });

  it("stamps the time a value was read", async () => {
    const { store, clock, settle } = controllableStore(0);
    store.load(["/brief"]);
    clock.advance(5_000);
    await settle("/brief", "b");
    expect(store.snapshot()["/brief"]?.fetchedAt).toBe(6_000);
  });
});

describe("desk store failures", () => {
  it("keeps the last good value when a read fails", async () => {
    const { store, settle } = controllableStore(0);
    let calls = 0;
    const seen: number[] = [];
    store.subscribe((state) => seen.push(Object.keys(state).length));
    const failing = createDeskStore<string>({
      refreshMs: 0,
      fetchDataset: async () => {
        calls += 1;
        if (calls === 1) return "good";
        throw new Error("the API fell over");
      },
    });
    failing.subscribe((state) => seen.push(Object.keys(state).length));
    failing.preload(["/brief"]);
    await flush();
    expect(failing.get("/brief")).toBe("good");

    failing.refresh();
    await flush();
    expect(failing.get("/brief")).toBe("good");
    expect(failing.isLoading("/brief")).toBe(false);
  });

  it("tells nobody about a failed read", async () => {
    const clock = testClock();
    const notifications: number[] = [];
    const store = createDeskStore<string>({
      refreshMs: 30_000,
      now: clock.now,
      timers: clock.timers,
      fetchDataset: async () => {
        throw new Error("nope");
      },
    });
    store.subscribe((state) => notifications.push(Object.keys(state).length));
    store.preload(["/brief"]);
    await flush();
    expect(notifications).toEqual([]);
  });

  it("treats a reader that throws as a failed read, not a crash", async () => {
    const clock = testClock();
    const store = createDeskStore<string>({
      refreshMs: 0,
      now: clock.now,
      timers: clock.timers,
      fetchDataset: () => {
        throw new Error("threw before returning a promise");
      },
    });
    store.load(["/brief"]);
    await flush();
    expect(store.get("/brief")).toBeUndefined();
    expect(store.isLoading("/brief")).toBe(false);
  });
});

describe("desk store stop", () => {
  it("clears the interval and aborts the open read", async () => {
    const { store, clock, aborted } = controllableStore(30_000);
    store.preload(["/brief"]);
    await flush();
    expect(clock.armed()).toBe(1);

    store.stop();
    expect(clock.armed()).toBe(0);
    expect(aborted).toEqual(["/brief"]);
  });

  it("throws away a read that lands after stop", async () => {
    const { store, settle } = controllableStore(30_000);
    store.preload(["/brief"]);
    await flush();
    store.stop();
    await settle("/brief", "late");
    expect(store.get("/brief")).toBeUndefined();
  });
});

describe("route lists", () => {
  const blocks = {
    brief: { route: "/brief", kind: "fields" },
    movers: { route: "/allocations/enriched", kind: "fields" },
    sleeves: { route: "/allocations/enriched", kind: "fields" },
    nav: { route: "/nav-series", kind: "fields" },
    canvas: { route: "/pipeline/runs/latest/graph", kind: "graph" },
  };

  it("lists each route once, in catalog order", () => {
    expect(uniqueRoutes(blocks)).toEqual([
      "/brief",
      "/allocations/enriched",
      "/nav-series",
      "/pipeline/runs/latest/graph",
    ]);
  });

  it("reads the same list from an array", () => {
    expect(uniqueRoutes([blocks.movers, blocks.nav, blocks.movers])).toEqual([
      "/allocations/enriched",
      "/nav-series",
    ]);
  });

  it("maps a route to the kind its reader needs", () => {
    const kinds = kindsByRoute(blocks);
    expect(kinds.get("/brief")).toBe("fields");
    expect(kinds.get("/pipeline/runs/latest/graph")).toBe("graph");
    expect(kinds.get("/nowhere")).toBeUndefined();
  });
});
