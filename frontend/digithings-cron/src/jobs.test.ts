import { describe, expect, it } from "vitest";
import { JOBS, jobsForCron, uniqueEnabledCrons } from "./jobs";

describe("jobsForCron", () => {
  it("matches exact cron strings only", () => {
    const jobs = jobsForCron("5 22 * * *");
    expect(jobs.map((j) => j.id)).toEqual(["research-metrics"]);
  });

  it("keeps twelve-x new_york on weekday-only cron", () => {
    const jobs = jobsForCron("17 12 * * MON-FRI");
    expect(jobs.map((j) => j.id)).toEqual(["twelve-x-new-york"]);
  });

  it("returns empty for unknown cron", () => {
    expect(jobsForCron("0 0 1 1 *")).toEqual([]);
  });

  it("at-open jobs have etOpenGate and mode at-open", () => {
    for (const cron of ["40 13 * * MON-FRI", "40 14 * * MON-FRI"]) {
      const jobs = jobsForCron(cron);
      expect(jobs).toHaveLength(1);
      expect(jobs[0].etOpenGate).toBe(true);
      expect(jobs[0].inputs?.mode).toBe("at-open");
    }
  });

  it("every enabled job cron is listed in uniqueEnabledCrons", () => {
    const set = new Set(uniqueEnabledCrons());
    for (const j of JOBS) {
      if (j.enabled) expect(set.has(j.cron)).toBe(true);
    }
  });

  it("workflow dispatches target the default develop branch", () => {
    for (const j of JOBS) {
      if (j.kind === "workflow_dispatch") expect(j.ref).toBe("develop");
      else expect(j.ref).toBeUndefined();
    }
  });

  it("market_context jobs pass bucket inputs", () => {
    expect(jobsForCron("4 */4 * * *")[0].inputs?.bucket).toBe("intraday");
    expect(jobsForCron("30 5 * * *")[0].inputs?.bucket).toBe("daily");
    expect(jobsForCron("8 7 * * SAT")[0].inputs?.bucket).toBe("weekly");
  });

  it("uses named weekdays so Cloudflare cannot reinterpret numeric DOWs", () => {
    for (const cron of uniqueEnabledCrons()) {
      const dow = cron.split(/\s+/)[4];
      expect(dow, cron).not.toMatch(/^\d(?:-\d)?$/);
    }
  });

  it("runs house research/portfolio retries every day without a Sunday special", () => {
    for (const [id, cron] of [
      ["house-run-09", "17 9 * * *"],
      ["house-run-10", "17 10 * * *"],
      ["house-run-11", "17 11 * * *"],
      ["house-run-12", "17 12 * * *"],
    ] as const) {
      expect(jobsForCron(cron).map((job) => job.id)).toEqual([id]);
    }
    expect(JOBS.some((job) => job.id === "house-run-sun")).toBe(false);
    expect(jobsForCron("17 12 * * SUN")).toEqual([]);
  });
});
