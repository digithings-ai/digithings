import { describe, expect, it, vi } from "vitest";

import { createDeskCache } from "./desk-cache";

/** A clock the test moves by hand, so freshness is measured, not waited on. */
function fakeClock(start = 1_000) {
  let t = start;
  return {
    now: () => t,
    advance: (ms: number) => {
      t += ms;
    },
  };
}

const deferred = <T>() => {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

describe("desk cache", () => {
  it("serves a fresh entry without reading again", async () => {
    const clock = fakeClock();
    const cache = createDeskCache<string>({ now: clock.now });
    const fetcher = vi.fn(async () => "book");

    expect(await cache.load("portfolio", fetcher)).toBe("book");
    expect(await cache.load("portfolio", fetcher)).toBe("book");

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(cache.size()).toBe(1);
  });

  it("deduplicates concurrent reads of the same key", async () => {
    const cache = createDeskCache<string>();
    const gate = deferred<string>();
    const fetcher = vi.fn(() => gate.promise);

    const first = cache.load("nav", fetcher);
    const second = cache.load("nav", fetcher);
    // Both callers must be waiting on the SAME read, not two.
    expect(fetcher).toHaveBeenCalledTimes(1);
    gate.resolve("series");
    expect(await first).toBe("series");
    expect(await second).toBe("series");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("keeps keys independent", async () => {
    const cache = createDeskCache<string>();
    const calls: string[] = [];
    const reader = (value: string) => async () => {
      calls.push(value);
      return value;
    };

    await Promise.all([cache.load("a", reader("a")), cache.load("b", reader("b"))]);

    expect(calls.sort()).toEqual(["a", "b"]);
    expect(cache.size()).toBe(2);
  });

  it("reads again once the window closes", async () => {
    const clock = fakeClock();
    const cache = createDeskCache<string>({ maxAgeMs: 100, now: clock.now });
    const fetcher = vi.fn(async () => "book");

    await cache.load("portfolio", fetcher);
    clock.advance(99);
    expect(await cache.load("portfolio", fetcher)).toBe("book");
    expect(fetcher).toHaveBeenCalledTimes(1);

    clock.advance(2);
    await cache.load("portfolio", fetcher);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("treats a zero window as always stale, so freshness is a gate and not a presence check", async () => {
    const cache = createDeskCache<string>({ maxAgeMs: 0 });
    const fetcher = vi.fn(async () => "book");

    await cache.load("portfolio", fetcher);
    await cache.load("portfolio", fetcher);

    expect(fetcher).toHaveBeenCalledTimes(2);
    // The value is still cached, just never fresh — presence alone must not satisfy `load`.
    expect(cache.peek("portfolio")).toBeUndefined();
    expect(cache.size()).toBe(1);
  });

  it("does not remember a failed read", async () => {
    const cache = createDeskCache<string>();
    const failing = vi.fn(async () => {
      throw new Error("withheld");
    });

    await expect(cache.load("brief", failing)).rejects.toThrow("withheld");
    expect(cache.size()).toBe(0);

    const retry = vi.fn(async () => "book");
    expect(await cache.load("brief", retry)).toBe("book");
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("retries after a failure instead of serving the rejected promise forever", async () => {
    const cache = createDeskCache<string>();
    const gate = deferred<string>();
    const failing = vi.fn(() => gate.promise);
    const retry = vi.fn(async () => "book");

    const first = cache.load("brief", failing);
    const shared = cache.load("brief", failing);
    expect(failing).toHaveBeenCalledTimes(1);

    gate.reject(new Error("withheld"));
    await expect(first).rejects.toThrow("withheld");
    await expect(shared).rejects.toThrow("withheld");

    expect(await cache.load("brief", retry)).toBe("book");
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("invalidates one key or all of them", async () => {
    const clock = fakeClock();
    const cache = createDeskCache<string>({ maxAgeMs: 10_000, now: clock.now });
    const portfolio = vi.fn(async () => "book");
    const brief = vi.fn(async () => "brief");

    await cache.load("portfolio", portfolio);
    await cache.load("brief", brief);
    expect(cache.size()).toBe(2);

    await cache.load("portfolio", portfolio);
    expect(portfolio).toHaveBeenCalledTimes(1);
    expect(brief).toHaveBeenCalledTimes(1);

    cache.invalidate("portfolio");
    expect(cache.size()).toBe(1);
    await cache.load("portfolio", portfolio);
    expect(portfolio).toHaveBeenCalledTimes(2);
    expect(brief).toHaveBeenCalledTimes(1);

    cache.invalidate();
    expect(cache.size()).toBe(0);
  });

  it("accepts a value set directly", async () => {
    const clock = fakeClock();
    const cache = createDeskCache<number>({ maxAgeMs: 50, now: clock.now });

    expect(cache.peek("preload")).toBeUndefined();
    cache.set("preload", 7);

    expect(cache.peek("preload")).toBe(7);
    clock.advance(51);
    expect(cache.peek("preload")).toBeUndefined();
  });
});
