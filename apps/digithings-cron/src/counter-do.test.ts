import { describe, expect, it } from "vitest";
import type { Env } from "./env";
import { StartCounter } from "./counter-do";

/**
 * Fake DurableObjectState. `transaction` really serialises: callers are chained
 * so two overlapping claimKey() calls cannot both observe an absent key. Without
 * it this harness cannot distinguish an atomic claim from a get-then-put race,
 * which is the whole reason the Durable Object exists.
 */
function fakeState() {
  const store = new Map<string, unknown>();
  let chain: Promise<unknown> = Promise.resolve();
  const txn = {
    async get<T>(k: string) { return store.get(k) as T | undefined; },
    async put(k: string, v: unknown) { store.set(k, v); },
    async delete(k: string) { store.delete(k); },
  };
  const storage = {
    async get<T>(k: string) { return store.get(k) as T | undefined; },
    async put(k: string, v: unknown) { store.set(k, v); },
    async delete(k: string) { store.delete(k); },
    async transaction<T>(cb: (t: typeof txn) => Promise<T>): Promise<T> {
      const run = chain.then(() => cb(txn));
      chain = run.then(() => undefined, () => undefined);
      return run;
    },
  };
  const state = { storage } as unknown as DurableObjectState;
  return { state, store };
}

function counter() {
  const { state } = fakeState();
  return new StartCounter(state, {} as Env);
}

describe("StartCounter", () => {
  it("counts two starts in the same minute as two", async () => {
    const c = counter();
    await c.record("twelve-x-session-catchup", "2026-09-28", "00:52", "00");
    await c.record("twelve-x-session-catchup", "2026-09-28", "00:52", "00");
    expect((await c.get("twelve-x-session-catchup", "2026-09-28")).total).toBe(2);
  });

  it("keys counts by job, by day, by minute and by hour", async () => {
    const c = counter();
    await c.record("twelve-x-session-catchup", "2026-09-28", "00:52", "00");
    await c.record("twelve-x-session-catchup", "2026-09-28", "01:52", "01");
    await c.record("prices-fx-refresh", "2026-09-28", "00:52", "00");
    const day = await c.get("twelve-x-session-catchup", "2026-09-28");
    expect(day.total).toBe(2);
    expect(day.byMinute).toEqual({ "00:52": 1, "01:52": 1 });
    expect(day.byHour).toEqual({ "00": 1, "01": 1 });
    expect((await c.get("prices-fx-refresh", "2026-09-28")).total).toBe(1);
    expect((await c.get("twelve-x-session-catchup", "2026-09-29")).total).toBe(0);
  });

  it("claims a key once and refuses it after", async () => {
    const c = counter();
    expect(await c.claimKey("twelve-x-session-catchup:1788000000000")).toBe(true);
    expect(await c.claimKey("twelve-x-session-catchup:1788000000000")).toBe(false);
  });

  it("releaseKey lets the key be claimed again", async () => {
    const c = counter();
    await c.claimKey("k");
    await c.releaseKey("k");
    expect(await c.claimKey("k")).toBe(true);
  });

  it("A.3 exactly one of two concurrent claims for the same key wins", async () => {
    const c = counter();
    const results = await Promise.all([c.claimKey("race"), c.claimKey("race")]);
    expect(results.filter(Boolean)).toHaveLength(1);
  });
});
