import { describe, expect, it } from "vitest";
import type { Env } from "./env";
import { StartCounter, SLOT_LEASE_MS } from "./counter-do";

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
    expect(await c.claimSlot(key, "2026-10-15T06:41")).toBe(true);
    expect(await c.claimSlot(key, "2026-10-15T06:41")).toBe(false);
  });

  it("hands the same row the next slot", async () => {
    const c = counter();
    const key = "41 6 * * *\ntoken-canary";
    expect(await c.claimSlot(key, "2026-10-15T06:41")).toBe(true);
    expect(await c.claimSlot(key, "2026-10-16T06:41")).toBe(true);
  });

  it("releaseSlot lets the slot be claimed again", async () => {
    const c = counter();
    const key = "k";
    await c.claimSlot(key, "2026-10-15T06:41");
    await c.releaseSlot(key, "2026-10-15T06:41");
    expect(await c.claimSlot(key, "2026-10-15T06:41")).toBe(true);
  });

  it("keeps a confirmed slot blocked past the lease", async () => {
    const c = counter();
    const key = "k";
    const slot = "2026-10-15T06:41";
    const base = 1_000_000;
    expect(await c.claimSlot(key, slot, base)).toBe(true);
    await c.confirmSlot(key, slot);
    expect(await c.claimSlot(key, slot, base + SLOT_LEASE_MS * 1000)).toBe(false);
  });

  it("re-claims an unconfirmed slot after the lease, so a dead delivery does not lose the tick", async () => {
    const c = counter();
    const key = "k";
    const slot = "2026-10-15T06:41";
    const base = 1_000_000;
    expect(await c.claimSlot(key, slot, base)).toBe(true);
    expect(await c.claimSlot(key, slot, base + SLOT_LEASE_MS - 1)).toBe(false);
    // The first delivery claimed and then died; the second may try the slot.
    expect(await c.claimSlot(key, slot, base + SLOT_LEASE_MS)).toBe(true);
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
    expect(await c.claimSlot("k", "2026-10-16T00:00")).toBe(true);
    // Late delivery of the previous day's last slot must not forget today.
    expect(await c.claimSlot("k", "2026-10-15T23:59")).toBe(true);
    expect(await c.claimSlot("k", "2026-10-16T00:00")).toBe(false);
  });

  it("A.3 exactly one of two concurrent claims for the same slot wins", async () => {
    const c = counter();
    const results = await Promise.all([
      c.claimSlot("race", "2026-10-15T06:41"),
      c.claimSlot("race", "2026-10-15T06:41"),
    ]);
    expect(results.filter(Boolean)).toHaveLength(1);
  });
});
