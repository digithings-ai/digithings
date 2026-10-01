import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { JOBS, jobsForCron, uniqueEnabledCrons } from "./jobs";

const PAUSED_PIPELINE_IDS = [
  "prices-at-open-13",
  "prices-at-open-14",
  "prices-fx-refresh",
  "prices-fx-refresh-sun",
  "prices-eod-macro",
  "market-data-refresh-morning",
  "market-data-refresh-evening",
  "house-run-09",
  "house-run-10",
  "house-run-11",
  "house-run-12",
  "research-metrics",
  "tearsheets",
  "onchain",
  "execution-cron-check",
  "continuous-improvement",
  "maintenance",
  "provider-review",
] as const;

const KEPT_ENABLED_IDS = [
  "agent-pr-finalizer",
  "agent-backlog-snapshot",
  "ci-pr-hygiene",
  "refresh-repo-activity",
  "project-enforce-assignment",
  "smoke-stack",
  "security-pip-audit",
  "security-npm-audit",
  "token-canary",
  "smoke-site",
  "twelve-x-asia",
  "twelve-x-london",
  "twelve-x-new-york",
  "twelve-x-market-context-intraday",
  "twelve-x-market-context-daily",
  "twelve-x-market-context-weekly",
  "twelve-x-performance-eval",
  "twelve-x-primemarket-heartbeat",
  "twelve-x-session-catchup",
  "twelve-x-archive-maintenance",
] as const;

describe("jobsForCron", () => {
  it("matches exact cron strings only", () => {
    expect(jobsForCron("5 22 * * *")).toEqual([]);
    expect(
      jobsForCron("5 22 * * *", { includeDisabled: true }).map((j) => j.id),
    ).toEqual(["research-metrics"]);
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
      expect(jobsForCron(cron)).toEqual([]);
      const jobs = jobsForCron(cron, { includeDisabled: true });
      expect(jobs).toHaveLength(1);
      expect(jobs[0].etOpenGate).toBe(true);
      expect(jobs[0].inputs?.mode).toBe("at-open");
      expect(jobs[0].enabled).toBe(false);
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
      expect(job?.enabled).toBe(false);
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
      expect(job?.enabled).toBe(false);
    }
  });

  it("sends house research/portfolio retries to digiquant-runner every day", () => {
    for (const [id, cron] of [
      ["house-run-09", "17 9 * * *"],
      ["house-run-10", "17 10 * * *"],
      ["house-run-11", "17 11 * * *"],
      ["house-run-12", "17 12 * * *"],
    ] as const) {
      expect(JOBS.find((job) => job.id === id)).toMatchObject({
        id,
        cron,
        kind: "container",
        workflow: "pipeline-digiquant.yml",
        command: "house-run",
        concurrency: "digiquant-pipeline",
        timeoutSeconds: 14400,
        codeRef: "main",
        enabled: false,
      });
      expect(jobsForCron(cron)).toEqual([]);
      expect(jobsForCron(cron, { includeDisabled: true }).map((job) => job.id)).toEqual([
        id,
      ]);
    }
    expect(JOBS.some((job) => job.id === "house-run-sun")).toBe(false);
    expect(jobsForCron("17 12 * * SUN")).toEqual([]);
  });

  it("sends smoke clocks to worker probes without a new cron", () => {
    expect(JOBS.find((job) => job.id === "smoke-site")).toMatchObject({
      kind: "probe",
      probe: "site",
      cron: "17 6 * * *",
      workflow: "smoke-site.yml",
      ref: "develop",
    });
    expect(JOBS.find((job) => job.id === "smoke-stack")).toMatchObject({
      kind: "probe",
      probe: "stack",
      cron: "27 7 * * *",
      workflow: "smoke-stack.yml",
      ref: "develop",
    });
    expect(JOBS.find((job) => job.id === "checkpoint-archive")).toBeUndefined();
    expect(uniqueEnabledCrons()).toContain("17 6 * * *");
    expect(uniqueEnabledCrons()).toContain("27 7 * * *");
    expect(uniqueEnabledCrons()).not.toContain("30 13 * * *");
  });

  it("pauses DigiQuant pipeline clocks and keeps non-pipeline jobs enabled", () => {
    expect(
      JOBS.filter((job) => !job.enabled)
        .map((job) => job.id)
        .sort(),
    ).toEqual([...PAUSED_PIPELINE_IDS].sort());
    expect(
      JOBS.filter((job) => job.enabled)
        .map((job) => job.id)
        .sort(),
    ).toEqual([...KEPT_ENABLED_IDS].sort());
    expect(uniqueEnabledCrons()).toHaveLength(20);
    expect(uniqueEnabledCrons()).toContain("17 12 * * MON-FRI");
    expect(uniqueEnabledCrons()).not.toContain("17 12 * * *");
    expect(uniqueEnabledCrons()).not.toContain("40 13 * * MON-FRI");
    expect(uniqueEnabledCrons()).not.toContain("8 22 * * SUN");
  });

  it("wrangler [triggers].crons matches uniqueEnabledCrons in order", () => {
    const toml = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "../wrangler.toml"),
      "utf8",
    );
    const block = toml.match(/\[triggers\]\s*crons\s*=\s*\[([\s\S]*?)\]/);
    expect(block).not.toBeNull();
    const wranglerCrons = [...block![1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
    expect(wranglerCrons).toEqual(uniqueEnabledCrons());
  });
});
