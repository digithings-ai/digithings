import { describe, expect, it } from "vitest";
import type { Env } from "./env";
import { BackfillLedger, ledgerKey } from "./backfill-do";

/**
 * Fake DurableObjectState. `transaction` really serialises: callers are chained
 * so two overlapping claim() calls cannot both observe an absent key. Without it
 * this harness cannot distinguish an atomic claim from a get-then-put race, which
 * is the entire reason the Durable Object exists.
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

function ledger() {
  const { state, store } = fakeState();
  return { l: new BackfillLedger(state, {} as Env), store };
}

describe("BackfillLedger", () => {
  it("uses a key prefix disjoint from StartCounter's counts: and claim:", () => {
    expect(ledgerKey("2026-06-02")).toBe("backfill:2026-06-02");
  });

  it("reports an unremediated date as unknown", async () => {
    const { l } = ledger();
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "unknown" });
  });

  it("claims a date it has never seen", async () => {
    const { l } = ledger();
    expect(await l.claim(["2026-06-02"], "2026-10-05T00:00:00Z", false)).toEqual({
      toDispatch: ["2026-06-02"],
      skipped: [],
    });
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "in_flight" });
  });

  it("skips a second claim on the same date while it is still in flight", async () => {
    const { l } = ledger();
    await l.claim(["2026-06-02"], "2026-10-05T00:00:00Z", false);
    // This is the surplus case: without the ledger both requests would write
    // the same date.
    expect(await l.claim(["2026-06-02"], "2026-10-05T00:01:00Z", false)).toEqual({
      toDispatch: [],
      skipped: ["2026-06-02"],
    });
  });

  it("marks a date done and then makes a repeat dispatch a no-op", async () => {
    const { l } = ledger();
    await l.claim(["2026-06-02"], "2026-10-05T00:00:00Z", false);
    await l.markDone(["2026-06-02"], "2026-10-05T00:02:00Z");
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "done" });
    // Idempotence per date: a repeat dispatch changes nothing.
    expect(await l.claim(["2026-06-02"], "2026-10-05T00:03:00Z", false)).toEqual({
      toDispatch: [],
      skipped: ["2026-06-02"],
    });
  });

  it("re-dispatches a done date when force_dates is set", async () => {
    const { l } = ledger();
    await l.claim(["2026-06-02"], "2026-10-05T00:00:00Z", false);
    await l.markDone(["2026-06-02"], "2026-10-05T00:02:00Z");
    expect(await l.claim(["2026-06-02"], "2026-10-05T00:04:00Z", true)).toEqual({
      toDispatch: ["2026-06-02"],
      skipped: [],
    });
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "in_flight" });
  });

  it("never steals a date that another request holds in flight, even when forced", async () => {
    const { l } = ledger();
    await l.claim(["2026-06-02"], "2026-10-05T00:00:00Z", false);
    expect(await l.claim(["2026-06-02"], "2026-10-05T00:05:00Z", true)).toEqual({
      toDispatch: [],
      skipped: ["2026-06-02"],
    });
  });

  it("partitions a mixed list so one stale date does not block the rest", async () => {
    const { l } = ledger();
    await l.claim(["2026-06-02"], "2026-10-05T00:00:00Z", false);
    await l.markDone(["2026-06-02"], "2026-10-05T00:01:00Z");
    expect(
      await l.claim(["2026-06-02", "2026-06-03", "2026-06-04"], "2026-10-05T00:06:00Z", false),
    ).toEqual({
      toDispatch: ["2026-06-03", "2026-06-04"],
      skipped: ["2026-06-02"],
    });
  });

  it("releases an in-flight claim on failure so the next request can retry", async () => {
    const { l } = ledger();
    await l.claim(["2026-06-02"], "2026-10-05T00:00:00Z", false);
    await l.release(["2026-06-02"]);
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "unknown" });
    expect(await l.claim(["2026-06-02"], "2026-10-05T00:07:00Z", false)).toEqual({
      toDispatch: ["2026-06-02"],
      skipped: [],
    });
  });

  it("does not release a date that is already done", async () => {
    const { l } = ledger();
    await l.claim(["2026-06-02"], "2026-10-05T00:00:00Z", false);
    await l.markDone(["2026-06-02"], "2026-10-05T00:02:00Z");
    await l.release(["2026-06-02"]);
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "done" });
  });

  it("lets exactly one of two overlapping claims win the same date", async () => {
    const { l } = ledger();
    const both = await Promise.all([
      l.claim(["2026-06-02"], "2026-10-05T00:00:00Z", false),
      l.claim(["2026-06-02"], "2026-10-05T00:00:01Z", false),
    ]);
    const winners = both.filter((r) => r.toDispatch.length === 1);
    expect(winners).toHaveLength(1);
    expect(both.filter((r) => r.skipped.length === 1)).toHaveLength(1);
  });

  it("keeps its storage keys disjoint from StartCounter's", async () => {
    const { l, store } = ledger();
    await l.claim(["2026-06-02"], "2026-10-05T00:00:00Z", false);
    expect([...store.keys()].every((k) => k.startsWith("backfill:"))).toBe(true);
    expect(store.has("counts:prices-at-open-13:2026-10-05")).toBe(false);
    expect(store.has("claim:prices-at-open-13:2026-10-05T13:40:00Z")).toBe(false);
  });
});
