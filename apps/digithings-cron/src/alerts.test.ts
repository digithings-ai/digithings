import { afterEach, describe, expect, it, vi } from "vitest";
import type { Env } from "./env";
import { JOBS } from "./jobs";
import { expectedCount } from "./expected";
import { checkShortDays } from "./alerts";

const DAY = "2026-09-28"; // a Monday, so the weekday-only clocks owe 24

/**
 * Every job reads as fully served except the ids named in `shortByJob`, which
 * read as `n`. Deriving the healthy count from expectedCount keeps the fixture
 * honest against the whole job table: a hardcoded "24 for everything" makes
 * every job with a denser cron (e.g. */15) look short and breaks the
 * exactly-one-message assertion for the wrong reason.
 */
function countingStub(shortByJob: Record<string, number>): Env {
  const ns = {
    get: () => ({
      get: async (jobId: string, day: string) => {
        const job = JOBS.find((j) => j.id === jobId);
        const expected = job ? expectedCount(job.cron, day, { now: new Date(`${day}T23:59:59Z`) }) : 0;
        const total = shortByJob[jobId] ?? expected;
        return { job: jobId, day, total, byMinute: {}, byHour: {} };
      },
    }),
  } as unknown as DurableObjectNamespace;
  return {
    GH_DISPATCH_TOKEN: "token",
    ALERT_ISSUE_REPO: "digithings-ai/digithings",
    ALERT_ISSUE_NUMBER: "1",
    START_COUNTER: ns,
  } as unknown as Env;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("checkShortDays", () => {
  it("A.6 a short day produces exactly one message", async () => {
    const fetchMock = vi.fn(async () => new Response("", { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const env = countingStub({ "twelve-x-session-catchup": 16 });

    const short = await checkShortDays(env, DAY);

    // exactly one short job, and exactly one message
    expect(short).toEqual([
      { job: "twelve-x-session-catchup", cron: "52 * * * MON-FRI", expected: 24, actual: 16 },
    ]);

    const forThatRepo = fetchMock.mock.calls.filter(([url]) => String(url).includes("issues/1/comments"));
    expect(forThatRepo).toHaveLength(1);

    const [url, init] = forThatRepo[0] as [string, RequestInit];
    expect(String(url)).toContain("digithings-ai/digithings/issues/1/comments");
    expect((init.headers as Record<string, string>).Authorization).toMatch(/^token /);
    // the body has to name the job and both numbers, or the operator cannot act on it
    const body = String(init.body);
    expect(body).toContain("twelve-x-session-catchup");
    expect(body).toContain("16");
    expect(body).toContain("24");
  });

  it("posts nothing when every job is fully served", async () => {
    const fetchMock = vi.fn(async () => new Response("", { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const env = countingStub({});
    expect(await checkShortDays(env, DAY)).toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a failed post does not throw and still returns the short days", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("network down"); }));
    const env = countingStub({ "twelve-x-session-catchup": 16 });
    const short = await checkShortDays(env, DAY);
    expect(short).toHaveLength(1);
    expect(short[0].actual).toBe(16);
  });
});
