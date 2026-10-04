import { describe, expect, it } from "vitest";
import type { Env } from "./env";
import type { StartRecord } from "./dispatch";
import { claimStart, readCounts, recordStart, releaseStart } from "./counts";
import { expectedCount } from "./expected";

const REC: StartRecord = {
  job: "twelve-x-session-catchup",
  cron: "52 * * * MON-FRI",
  scheduledMinute: "00:52",
  repo: "digithings-ai/twelve-x",
  workflow: "session_catchup.yml",
  result: "accepted",
  githubStatus: 204,
  startKey: "twelve-x-session-catchup:0",
};

function stubCounter() {
  const state = { total: 0, byMinute: {}, byHour: {}, claimed: new Set<string>() };
  const ns = {
    get: () => ({
      record: async (job: string, day: string, minute: string, hour: string) => {
        state.total += 1;
        state.byMinute[minute] = (state.byMinute[minute] ?? 0) + 1;
        state.byHour[hour] = (state.byHour[hour] ?? 0) + 1;
      },
      get: async (job: string, day: string) => ({
        job, day, total: state.total, byMinute: state.byMinute, byHour: state.byHour,
      }),
      claimKey: async (k: string) => !state.claimed.has(k) && (state.claimed.add(k), true),
      releaseKey: async (k: string) => { state.claimed.delete(k); },
    }),
  } as unknown as DurableObjectNamespace;
  return { state, env: { START_COUNTER: ns } as Env };
}

describe("counts", () => {
  it("A.1 the minutes recorded for one working day match the cron's minutes", async () => {
    const { env } = stubCounter();
    for (let h = 0; h < 24; h += 1) {
      await recordStart(env, { ...REC, scheduledMinute: `${String(h).padStart(2, "0")}:52` });
    }
    const counts = await readCounts(env, "twelve-x-session-catchup", "2026-09-28");
    expect(counts.total).toBe(24);
    expect(Object.keys(counts.byMinute)).toHaveLength(24);
    expect(Object.keys(counts.byMinute)).toContain("00:52");
    expect(Object.keys(counts.byMinute)).toContain("23:52");
    // cross-check against the reference the alarm will use
    expect(counts.total).toBe(expectedCount("52 * * * MON-FRI", "2026-09-28", { now: new Date("2026-09-28T23:59:59Z") }));
  });

  it("A.8 a failing counter does not change the start result", async () => {
    const env = {
      START_COUNTER: { get: () => ({ record: async () => { throw new Error("DO down"); } }) },
    } as unknown as Env;
    await expect(recordStart(env, REC)).resolves.toBeUndefined();
  });

  it("claimStart is true once and false after", async () => {
    const { env } = stubCounter();
    expect(await claimStart(env, "twelve-x-session-catchup:123")).toBe(true);
    expect(await claimStart(env, "twelve-x-session-catchup:123")).toBe(false);
  });

  it("releaseStart lets a claimed key be claimed again", async () => {
    const { env } = stubCounter();
    expect(await claimStart(env, "twelve-x-session-catchup:456")).toBe(true);
    await releaseStart(env, "twelve-x-session-catchup:456");
    expect(await claimStart(env, "twelve-x-session-catchup:456")).toBe(true);
  });
});
