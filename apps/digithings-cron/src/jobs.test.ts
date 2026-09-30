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
      if (j.kind === "repository_dispatch") expect(j.ref).toBeUndefined();
      else expect(j.ref).toBe("develop");
    }
  });

  it("sends price and market-data clocks to digiquant-runner", () => {
    expect(JOBS.some((job) => job.id === "prices-intraday")).toBe(false);
    const fx = JOBS.find((job) => job.id === "prices-fx-refresh");
    expect(fx?.kind).toBe("container");
    expect(fx?.command).toBe("prices-fx-candles");
    expect(fx?.codeRef).toBe("main");
    expect(JSON.stringify(fx?.command)).not.toContain("fetch-macro");
    const morning = JOBS.find((job) => job.id === "market-data-refresh-morning");
    const evening = JOBS.find((job) => job.id === "market-data-refresh-evening");
    expect(morning?.cron).toBe("0 13 * * *");
    expect(evening?.cron).toBe("30 21 * * *");
    expect(morning?.command).toBe("market-data-refresh");
    expect(evening?.command).toBe("market-data-refresh");
    expect(morning?.concurrency).toBe("market-data-refresh");
    for (const job of [morning, evening, fx]) {
      expect(job?.kind).toBe("container");
      expect(job?.workflow).toBeTruthy();
      expect(job?.ref).toBe("develop");
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

  it("sends phase 2 clocks to digiquant-runner without a second schedule", () => {
    const expected = [
      ["onchain", "onchain-bitview", "40 22 * * *", 900],
      ["tearsheets", "tearsheets", "12 0 * * *", 2700],
      ["research-metrics", "research-metrics", "5 22 * * *", 1200],
      ["execution-cron-check", "execution-cron-check", "15 12 * * *", 600],
    ] as const;
    for (const [id, command, cron, timeout] of expected) {
      const job = JOBS.find((row) => row.id === id);
      expect(job?.kind).toBe("container");
      expect(job?.command).toBe(command);
      expect(job?.cron).toBe(cron);
      expect(job?.timeoutSeconds).toBe(timeout);
      expect(job?.codeRef).toBe("main");
      expect(job?.workflow).toBeTruthy();
      expect(job?.ref).toBe("develop");
    }
    expect(JOBS.find((job) => job.id === "house-run-09")?.kind).toBe("repository_dispatch");
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
