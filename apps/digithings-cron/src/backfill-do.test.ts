import { describe, expect, it, vi } from "vitest";
import type { Env } from "./env";
import { BackfillLedger, IN_FLIGHT_TTL_MS, ledgerKey } from "./backfill-do";

const T0 = "2026-10-05T00:00:00Z";
/** One minute either side of the in-flight window, so a TTL change cannot silently pass. */
const INSIDE_TTL = new Date(Date.parse(T0) + IN_FLIGHT_TTL_MS - 60_000).toISOString();
const PAST_TTL = new Date(Date.parse(T0) + IN_FLIGHT_TTL_MS + 60_000).toISOString();

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
    const split = await l.claim(["2026-06-02"], T0, false);
    expect(split).toEqual({
      toDispatch: ["2026-06-02"],
      skipped: [],
      claimedAt: T0,
    });
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "in_flight" });
  });

  it("hands out a token that matches the claimed_at it stored", async () => {
    // The token is the fence every settle and release is checked against, so it
    // has to be the value on disk and not a separate clock reading.
    const { l, store } = ledger();
    const split = await l.claim(["2026-06-02"], T0, false);
    expect(store.get(ledgerKey("2026-06-02"))).toMatchObject({ claimed_at: split.claimedAt });
  });

  it("skips a second claim on the same date while it is still in flight", async () => {
    const { l } = ledger();
    await l.claim(["2026-06-02"], T0, false);
    // This is the surplus case: without the ledger both requests would write
    // the same date.
    expect(await l.claim(["2026-06-02"], "2026-10-05T00:01:00Z", false)).toEqual({
      toDispatch: [],
      skipped: ["2026-06-02"],
      claimedAt: "2026-10-05T00:01:00Z",
    });
  });

  it("marks a date done and then makes a repeat dispatch a no-op", async () => {
    const { l } = ledger();
    const split = await l.claim(["2026-06-02"], T0, false);
    await l.markDone(["2026-06-02"], "2026-10-05T00:02:00Z", split.claimedAt);
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "done" });
    // Idempotence per date: a repeat dispatch changes nothing.
    expect(await l.claim(["2026-06-02"], "2026-10-05T00:03:00Z", false)).toEqual({
      toDispatch: [],
      skipped: ["2026-06-02"],
      claimedAt: "2026-10-05T00:03:00Z",
    });
  });

  it("re-dispatches a done date when force_dates is set", async () => {
    const { l } = ledger();
    const first = await l.claim(["2026-06-02"], T0, false);
    await l.markDone(["2026-06-02"], "2026-10-05T00:02:00Z", first.claimedAt);
    expect(await l.claim(["2026-06-02"], "2026-10-05T00:04:00Z", true)).toEqual({
      toDispatch: ["2026-06-02"],
      skipped: [],
      claimedAt: "2026-10-05T00:04:00Z",
    });
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "in_flight" });
  });

  it("remembers a forced reclaim came from done, so a decline can put it back", async () => {
    const { l, store } = ledger();
    const first = await l.claim(["2026-06-02"], T0, false);
    await l.markDone(["2026-06-02"], "2026-10-05T00:02:00Z", first.claimedAt);
    await l.claim(["2026-06-02"], "2026-10-05T00:04:00Z", true);
    expect(store.get(ledgerKey("2026-06-02"))).toMatchObject({
      state: "in_flight",
      reclaimed_from: "done",
      completed_at: "2026-10-05T00:02:00Z",
    });
  });

  it("keeps a remediated date remediated when a forced re-dispatch is declined", async () => {
    // The bug: a forced claim over a `done` date, then a benign 422, used to
    // demote the date to `dispatch_suppressed` — discarding the fact that a run
    // exists. The next plain POST then re-dispatched it, which is the DIG-48
    // surplus this whole endpoint exists to prevent. Reachable today because
    // twelve-x maintenance.yml is disabled, so every forced POST takes the 422
    // branch.
    const { l } = ledger();
    const first = await l.claim(["2026-06-02"], T0, false);
    await l.markDone(["2026-06-02"], "2026-10-05T00:02:00Z", first.claimedAt);

    const forced = await l.claim(["2026-06-02"], "2026-10-05T00:04:00Z", true);
    await l.markSuppressed(["2026-06-02"], "2026-10-05T00:05:00Z", 422, forced.claimedAt);

    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "done" });
  });

  it("keeps the original completed_at when a forced reclaim is declined", async () => {
    const { l, store } = ledger();
    const first = await l.claim(["2026-06-02"], T0, false);
    await l.markDone(["2026-06-02"], "2026-10-05T00:02:00Z", first.claimedAt);
    const forced = await l.claim(["2026-06-02"], "2026-10-05T00:04:00Z", true);
    await l.markSuppressed(["2026-06-02"], "2026-10-05T00:05:00Z", 422, forced.claimedAt);
    expect(store.get(ledgerKey("2026-06-02"))).toEqual({
      state: "done",
      claimed_at: "2026-10-05T00:04:00Z",
      completed_at: "2026-10-05T00:02:00Z",
    });
  });

  it("leaves a plain suppressed date claimable, unlike a declined forced one", async () => {
    const { l } = ledger();
    const split = await l.claim(["2026-06-02"], T0, false);
    await l.markSuppressed(["2026-06-02"], "2026-10-05T00:05:00Z", 422, split.claimedAt);
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "dispatch_suppressed" });
  });

  it("clears reclaimed_from once a forced re-dispatch succeeds", async () => {
    const { l, store } = ledger();
    const first = await l.claim(["2026-06-02"], T0, false);
    await l.markDone(["2026-06-02"], "2026-10-05T00:02:00Z", first.claimedAt);
    const forced = await l.claim(["2026-06-02"], "2026-10-05T00:04:00Z", true);
    await l.markDone(["2026-06-02"], "2026-10-05T00:06:00Z", forced.claimedAt);
    expect(store.get(ledgerKey("2026-06-02"))).toEqual({
      state: "done",
      claimed_at: "2026-10-05T00:04:00Z",
      completed_at: "2026-10-05T00:06:00Z",
    });
  });

  it("never steals a date that another request holds in flight, even when forced", async () => {
    const { l } = ledger();
    await l.claim(["2026-06-02"], T0, false);
    expect(await l.claim(["2026-06-02"], "2026-10-05T00:05:00Z", true)).toEqual({
      toDispatch: [],
      skipped: ["2026-06-02"],
      claimedAt: "2026-10-05T00:05:00Z",
    });
  });

  it("keeps a suppressed dispatch claimable, so the next request retries it", async () => {
    const { l } = ledger();
    const split = await l.claim(["2026-06-02"], T0, false);
    // GitHub answered 422: no run started, so this date is still owed a backfill.
    await l.markSuppressed(["2026-06-02"], "2026-10-05T00:01:00Z", 422, split.claimedAt);
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "dispatch_suppressed" });

    // The retry path: the workflow being re-enabled turns into a dispatch.
    const retry = await l.claim(["2026-06-02"], "2026-10-05T00:04:00Z", false);
    expect(retry).toEqual({
      toDispatch: ["2026-06-02"],
      skipped: [],
      claimedAt: "2026-10-05T00:04:00Z",
    });
    await l.markDone(["2026-06-02"], "2026-10-05T00:05:00Z", retry.claimedAt);
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "done" });
  });

  it("keeps the suppressed GitHub status for diagnosis", async () => {
    const { l, store } = ledger();
    const split = await l.claim(["2026-06-02"], T0, false);
    await l.markSuppressed(["2026-06-02"], "2026-10-05T00:01:00Z", 422, split.claimedAt);
    expect(store.get(ledgerKey("2026-06-02"))).toMatchObject({
      state: "dispatch_suppressed",
      suppressed_at: "2026-10-05T00:01:00Z",
      github_status: 422,
    });
  });

  it("ages out a claim left behind by a request that never settled", async () => {
    const { l } = ledger();
    await l.claim(["2026-06-02"], T0, false);
    // Killed between claim and settle: no release, no markDone, and no operator
    // retry. Without an age-out this date is locked out forever and every later
    // POST reports it as remediated.
    expect(await l.claim(["2026-06-02"], INSIDE_TTL, false)).toEqual({
      toDispatch: [],
      skipped: ["2026-06-02"],
      claimedAt: INSIDE_TTL,
    });
    expect(await l.claim(["2026-06-02"], PAST_TTL, false)).toEqual({
      toDispatch: ["2026-06-02"],
      skipped: [],
      claimedAt: PAST_TTL,
    });
  });

  it("lets a forced request reclaim a stale claim", async () => {
    const { l } = ledger();
    await l.claim(["2026-06-02"], T0, false);
    expect(await l.claim(["2026-06-02"], PAST_TTL, true)).toEqual({
      toDispatch: ["2026-06-02"],
      skipped: [],
      claimedAt: PAST_TTL,
    });
  });

  it("treats an unparseable claimed_at as abandoned rather than a lockout", async () => {
    const { l, store } = ledger();
    store.set(ledgerKey("2026-06-02"), { state: "in_flight", claimed_at: "not-a-date" });
    expect(await l.claim(["2026-06-02"], T0, false)).toEqual({
      toDispatch: ["2026-06-02"],
      skipped: [],
      claimedAt: T0,
    });
  });

  it("partitions a mixed list so one stale date does not block the rest", async () => {
    const { l } = ledger();
    const first = await l.claim(["2026-06-02"], T0, false);
    await l.markDone(["2026-06-02"], "2026-10-05T00:01:00Z", first.claimedAt);
    expect(
      await l.claim(["2026-06-02", "2026-06-03", "2026-06-04"], "2026-10-05T00:06:00Z", false),
    ).toEqual({
      toDispatch: ["2026-06-03", "2026-06-04"],
      skipped: ["2026-06-02"],
      claimedAt: "2026-10-05T00:06:00Z",
    });
  });

  it("releases an in-flight claim on failure so the next request can retry", async () => {
    const { l } = ledger();
    const split = await l.claim(["2026-06-02"], T0, false);
    await l.release(["2026-06-02"], split.claimedAt);
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "unknown" });
    expect(await l.claim(["2026-06-02"], "2026-10-05T00:07:00Z", false)).toEqual({
      toDispatch: ["2026-06-02"],
      skipped: [],
      claimedAt: "2026-10-05T00:07:00Z",
    });
  });

  it("does not release a date that is already done", async () => {
    const { l } = ledger();
    const split = await l.claim(["2026-06-02"], T0, false);
    await l.markDone(["2026-06-02"], "2026-10-05T00:02:00Z", split.claimedAt);
    await l.release(["2026-06-02"], split.claimedAt);
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "done" });
  });

  it("does not release a suppressed date, which is still owed a backfill", async () => {
    const { l } = ledger();
    const split = await l.claim(["2026-06-02"], T0, false);
    await l.markSuppressed(["2026-06-02"], "2026-10-05T00:01:00Z", 422, split.claimedAt);
    await l.release(["2026-06-02"], split.claimedAt);
    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "dispatch_suppressed" });
  });

  it("lets exactly one of two overlapping claims win the same date", async () => {
    const { l } = ledger();
    const both = await Promise.all([
      l.claim(["2026-06-02"], T0, false),
      l.claim(["2026-06-02"], "2026-10-05T00:00:01Z", false),
    ]);
    const winners = both.filter((r) => r.toDispatch.length === 1);
    expect(winners).toHaveLength(1);
    expect(both.filter((r) => r.skipped.length === 1)).toHaveLength(1);
  });

  it("keeps its storage keys disjoint from StartCounter's", async () => {
    const { l, store } = ledger();
    await l.claim(["2026-06-02"], T0, false);
    expect([...store.keys()].every((k) => k.startsWith("backfill:"))).toBe(true);
    expect(store.has("counts:prices-at-open-13:2026-10-05")).toBe(false);
    expect(store.has("claim:prices-at-open-13:2026-10-05T13:40:00Z")).toBe(false);
  });
});

describe("BackfillLedger — a settle only writes the caller's own claim", () => {
  /**
   * The whole point of the token: a request that took longer than the in-flight
   * window must not touch a claim that has since been re-dispatched by somebody
   * else. Without the fence, request B's release erases request A's live claim
   * and the next plain POST re-dispatches a date that already has a run.
   */
  it("will not release a claim that has since been re-dispatched", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { l } = ledger();
    const a = await l.claim(["2026-06-02"], T0, false);
    // A's claim ages out and B takes the date.
    const b = await l.claim(["2026-06-02"], PAST_TTL, false);
    await l.release(["2026-06-02"], a.claimedAt);

    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "in_flight" });
    expect(b.toDispatch).toEqual(["2026-06-02"]);
    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('"reason":"claim_not_owned"'),
    );
  });

  it("will not mark done a claim that has since been re-dispatched", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { l } = ledger();
    const a = await l.claim(["2026-06-02"], T0, false);
    await l.claim(["2026-06-02"], PAST_TTL, false);
    await l.markDone(["2026-06-02"], "2026-10-05T00:40:00Z", a.claimedAt);

    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "in_flight" });
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('"reason":"claim_not_owned"'));
  });

  it("will not suppress a claim that has since been re-dispatched", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { l } = ledger();
    const a = await l.claim(["2026-06-02"], T0, false);
    await l.claim(["2026-06-02"], PAST_TTL, false);
    await l.markSuppressed(["2026-06-02"], "2026-10-05T00:40:00Z", 422, a.claimedAt);

    expect(await l.status(["2026-06-02"])).toEqual({ "2026-06-02": "in_flight" });
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('"reason":"claim_not_owned"'));
  });

  it("logs a settle on a date whose record is gone instead of dropping it", async () => {
    // Before the fence this was a bare `continue`: a date left with no record
    // although a run existed for it, with nothing in the logs to notice it by.
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { l, store } = ledger();
    const split = await l.claim(["2026-06-02"], T0, false);
    store.delete(ledgerKey("2026-06-02"));
    await l.markDone(["2026-06-02"], "2026-10-05T00:02:00Z", split.claimedAt);

    expect(warn).toHaveBeenCalledWith(expect.stringContaining('"reason":"record_missing"'));
  });

  it("still settles its own claim after a neighbour's late settle was fenced off", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { l } = ledger();
    const a = await l.claim(["2026-06-02", "2026-06-03"], T0, false);
    const b = await l.claim(["2026-06-03"], PAST_TTL, false);
    // B is late and loses its write; A's write still lands.
    await l.markDone(["2026-06-03"], "2026-10-05T00:41:00Z", b.claimedAt);
    await l.markDone(["2026-06-02", "2026-06-03"], "2026-10-05T00:42:00Z", a.claimedAt);
    expect(await l.status(["2026-06-02", "2026-06-03"])).toEqual({
      "2026-06-02": "done",
      "2026-06-03": "done",
    });
  });
});