import { describe, expect, it } from "vitest";
import type { Env } from "./env";
import { StartCounter, DISPATCH_LEASE_MS, SLOT_LEASE_MS } from "./counter-do";

/**
 * Fake DurableObjectState. `transaction` really serialises: callers are chained
 * so two overlapping claimSlot() calls cannot both observe an absent slot. Without
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

  it("claims a slot once and refuses it after", async () => {
    const c = counter();
    const key = "41 6 * * *\ntoken-canary";
    expect(await c.claimSlot(key, "2026-10-15T06:41")).toEqual(expect.any(String));
    expect(await c.claimSlot(key, "2026-10-15T06:41")).toBeNull();
  });

  it("hands the same row the next slot", async () => {
    const c = counter();
    const key = "41 6 * * *\ntoken-canary";
    expect(await c.claimSlot(key, "2026-10-15T06:41")).toEqual(expect.any(String));
    expect(await c.claimSlot(key, "2026-10-16T06:41")).toEqual(expect.any(String));
  });

  it("releaseSlot lets the slot be claimed again", async () => {
    const c = counter();
    const key = "k";
    const token = await c.claimSlot(key, "2026-10-15T06:41");
    await c.releaseSlot(key, "2026-10-15T06:41", token!);
    expect(await c.claimSlot(key, "2026-10-15T06:41")).toEqual(expect.any(String));
  });

  it("keeps a confirmed slot blocked past the lease", async () => {
    const c = counter();
    const key = "k";
    const slot = "2026-10-15T06:41";
    const base = 1_000_000;
    const token = await c.claimSlot(key, slot, base);
    await c.confirmSlot(key, slot, token!);
    expect(await c.claimSlot(key, slot, base + DISPATCH_LEASE_MS * 1000)).toBeNull();
  });

  it("re-claims a claim that never dispatched after the short lease", async () => {
    const c = counter();
    const key = "k";
    const slot = "2026-10-15T06:41";
    const base = 1_000_000;
    expect(await c.claimSlot(key, slot, base)).toEqual(expect.any(String));
    expect(await c.claimSlot(key, slot, base + SLOT_LEASE_MS - 1)).toBeNull();
    // The first delivery claimed and then died before it started the dispatch.
    expect(await c.claimSlot(key, slot, base + SLOT_LEASE_MS)).toEqual(expect.any(String));
  });

  it("holds a dispatch in flight past the short lease, so a slow GitHub call is not doubled", async () => {
    const c = counter();
    const key = "k";
    const slot = "2026-10-15T06:41";
    const base = 1_000_000;
    const token = await c.claimSlot(key, slot, base);
    expect(await c.markDispatching(key, slot, token!, base)).toBe(true);
    // The ordinary second delivery arrives 7-29s later, with the first POST
    // still open. It must not take the slot.
    expect(await c.claimSlot(key, slot, base + 29_000)).toBeNull();
    expect(await c.claimSlot(key, slot, base + DISPATCH_LEASE_MS - 1)).toBeNull();
    // Only a dispatch that outlived the long lease can be treated as dead.
    expect(await c.claimSlot(key, slot, base + DISPATCH_LEASE_MS)).toEqual(expect.any(String));
  });

  it("fences release and confirm, so a late owner cannot touch the new claim", async () => {
    const c = counter();
    const key = "k";
    const slot = "2026-10-15T06:41";
    const base = 1_000_000;
    const first = await c.claimSlot(key, slot, base);
    expect(await c.markDispatching(key, slot, first!, base)).toBe(true);
    // First dispatch is treated as dead after the long lease.
    const second = await c.claimSlot(key, slot, base + DISPATCH_LEASE_MS);
    expect(second).toEqual(expect.any(String));
    expect(second).not.toBe(first);

    // The stale owner now fails and releases, and also confirms late: neither
    // may remove or speak for the second owner's claim.
    await c.releaseSlot(key, slot, first!);
    await c.confirmSlot(key, slot, first!);
    expect(await c.claimSlot(key, slot, base + DISPATCH_LEASE_MS + 1)).toBeNull();
  });

  it("drops the previous day's slots, so an every-minute clock cannot grow forever", async () => {
    const { state, store } = fakeState();
    const c = new StartCounter(state, {} as Env);
    await c.claimSlot("prices-fx-refresh", "2026-10-15T00:19");
    const dayOne = [...store.keys()].filter((k) => k.startsWith("slots:"));
    expect(dayOne).toHaveLength(1);

    await c.claimSlot("prices-fx-refresh", "2026-10-16T00:19");
    const dayTwo = [...store.keys()].filter((k) => k.startsWith("slots:"));
    expect(dayTwo).toHaveLength(1);
    expect(dayTwo[0]).toContain("2026-10-16");
  });

  it("keeps the newer day's slots when a 23:59 tick is delivered after midnight", async () => {
    const { state } = fakeState();
    const c = new StartCounter(state, {} as Env);
    expect(await c.claimSlot("k", "2026-10-16T00:00")).toEqual(expect.any(String));
    // Late delivery of the previous day's last slot must not forget today.
    expect(await c.claimSlot("k", "2026-10-15T23:59")).toEqual(expect.any(String));
    expect(await c.claimSlot("k", "2026-10-16T00:00")).toBeNull();
  });

  it("A.3 exactly one of two concurrent claims for the same slot wins", async () => {
    const c = counter();
    const results = await Promise.all([
      c.claimSlot("race", "2026-10-15T06:41"),
      c.claimSlot("race", "2026-10-15T06:41"),
    ]);
    expect(results.filter((token) => token !== null)).toHaveLength(1);
  });
});
