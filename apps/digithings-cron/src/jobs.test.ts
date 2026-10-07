import { describe, expect, it } from "vitest";
import { JOBS, jobsForCron, uniqueEnabledCrons } from "./jobs";

const RESUMED_PIPELINE_IDS = [
  "prices-at-open-13",
  "prices-at-open-14",
  "prices-fx-refresh",
  "prices-fx-refresh-sun",
  "prices-eod-macro",
  "market-data-refresh-morning",
  "market-data-refresh-evening",
  "checkpoint-archive",
  "house-run-09",
  "research-metrics",
  "tearsheets",
  "onchain",
  "execution-cron-check",
  "continuous-improvement",
  "maintenance",
  "provider-review",
] as const;

const DISABLED_HOUSE_RETRY_IDS = ["house-run-10", "house-run-11", "house-run-12"] as const;

const PATH_A_TRAP_IDS = [
  "agent-pr-finalizer",
  "agent-backlog-snapshot",
  "refresh-repo-activity",
  "project-enforce-assignment",
] as const;

const PATH_A_ENABLED_IDS = [
  "agent-pr-finalizer",
  "agent-backlog-snapshot",
  "ci-pr-hygiene",
  "refresh-repo-activity",
  "project-enforce-assignment",
  "smoke-stack",
  "security-pip-audit",
  "security-npm-audit",
  "token-canary",
  "secret-staleness",
  "dependency-freshness",
  "smoke-site",
  "datatap-answer-check",
] as const;

const TWELVE_X_ENABLED_IDS = [
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
  "twelve-x-digisearch-parity",
] as const;

const ENABLED_CRONS = [
  "40 13 * * MON-FRI",
  "40 14 * * MON-FRI",
  "19 */2 * * MON-FRI",
  "19 22 * * SUN",
  "27 21 * * MON-FRI",
  "0 13 * * *",
  "30 13 * * *",
  "30 21 * * *",
  "17 9 * * MON",
  "5 22 * * *",
  "12 0 * * *",
  "40 22 * * *",
  "15 12 * * *",
  "8 22 * * SUN",
  "8 8 * * MON",
  "9 0 * * SUN",
  "11 7 * * *",
  "13 6 * * MON",
  "21 6 * * *",
  "10 6 * * MON",
  "23 9 * * *",
  "27 7 * * *",
  "33 6 * * MON",
  "37 6 * * MON",
  "41 6 * * *",
  "17 6 1 * *",
  "23 6 1 * *",
  "17 6 * * *",
  "17 * * * *",
  "7 0 * * MON-FRI",
  "12 7 * * MON-FRI",
  "17 12 * * MON-FRI",
  "4 */4 * * *",
  "30 5 * * *",
  "8 7 * * SAT",
  "30 17 * * MON-FRI",
  "3 6,18 * * *",
  "52 * * * MON-FRI",
  "30 2 * * *",
  "8 9 * * MON",
] as const;

describe("jobsForCron", () => {
  it("matches exact cron strings only", () => {
    expect(jobsForCron("5 22 * * *").map((j) => j.id)).toEqual(["research-metrics"]);
  });

  it("keeps twelve-x new_york on weekday-only cron", () => {
    const jobs = jobsForCron("17 12 * * MON-FRI");
    expect(jobs.map((j) => j.id)).toEqual(["twelve-x-new-york"]);
    expect(jobs[0].enabled).toBe(true);
    expect(jobsForCron("17 12 * * *")).toEqual([]);
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
      expect(jobs[0].enabled).toBe(true);
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
      expect(job?.enabled).toBe(true);
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
      expect(job?.enabled).toBe(true);
    }
  });

  it("collapses house-run to one Monday-morning clock", () => {
    expect(JOBS.find((job) => job.id === "house-run-09")).toMatchObject({
      id: "house-run-09",
      cron: "17 9 * * MON",
      kind: "container",
      workflow: "pipeline-digiquant.yml",
      command: "house-run",
      concurrency: "digiquant-pipeline",
      timeoutSeconds: 14400,
      codeRef: "main",
      enabled: true,
    });
    expect(jobsForCron("17 9 * * MON").map((job) => job.id)).toEqual(["house-run-09"]);
    expect(jobsForCron("17 9 * * *")).toEqual([]);
    for (const [id, cron] of [
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
    expect(uniqueEnabledCrons()).toContain("17 6 * * *");
    expect(uniqueEnabledCrons()).toContain("27 7 * * *");
  });

  it("wires checkpoint-archive to digiquant-runner at 13:30 UTC", () => {
    expect(JOBS.find((job) => job.id === "checkpoint-archive")).toMatchObject({
      kind: "container",
      command: "checkpoint-archive",
      concurrency: "checkpoint-archive",
      timeoutSeconds: 3600,
      cron: "30 13 * * *",
      workflow: "pipeline-checkpoint-archive.yml",
      ref: "develop",
      codeRef: "main",
      enabled: true,
    });
    expect(jobsForCron("30 13 * * *").map((job) => job.id)).toEqual(["checkpoint-archive"]);
    expect(uniqueEnabledCrons()).toContain("30 13 * * *");
  });

  it("resumes twelve-x clocks and Path A traps; weekly Mon house-run only", () => {
    expect(
      JOBS.filter((job) => !job.enabled)
        .map((job) => job.id)
        .sort(),
    ).toEqual([...DISABLED_HOUSE_RETRY_IDS].sort());
    expect(
      JOBS.filter((job) => job.enabled)
        .map((job) => job.id)
        .sort(),
    ).toEqual(
      [...RESUMED_PIPELINE_IDS, ...PATH_A_ENABLED_IDS, ...TWELVE_X_ENABLED_IDS].sort(),
    );
    expect(uniqueEnabledCrons()).toEqual([...ENABLED_CRONS]);
    expect(uniqueEnabledCrons()).toContain("17 12 * * MON-FRI");
    expect(uniqueEnabledCrons()).not.toContain("17 12 * * *");
    expect(uniqueEnabledCrons()).not.toContain("17 9 * * *");
    expect(uniqueEnabledCrons()).not.toContain("17 10 * * *");
    expect(uniqueEnabledCrons()).not.toContain("17 11 * * *");
    expect(uniqueEnabledCrons()).toContain("17 9 * * MON");
    expect(uniqueEnabledCrons()).toContain("40 13 * * MON-FRI");
    expect(uniqueEnabledCrons()).toContain("8 22 * * SUN");
    expect(uniqueEnabledCrons()).toContain("11 7 * * *");
    expect(uniqueEnabledCrons()).toContain("13 6 * * MON");
    expect(uniqueEnabledCrons()).toContain("10 6 * * MON");
    expect(uniqueEnabledCrons()).toContain("23 9 * * *");
    const finalizer = JOBS.find((job) => job.id === "agent-pr-finalizer");
    expect(finalizer).toMatchObject({
      kind: "workflow_dispatch",
      workflow: "agent-pr-finalizer.yml",
      cron: "11 7 * * *",
      enabled: true,
      inputs: { dry_run: "false" },
      repo: "digithings-ai/digithings",
    });
    for (const id of PATH_A_TRAP_IDS) {
      const job = JOBS.find((row) => row.id === id);
      expect(job?.enabled).toBe(true);
      expect(job?.kind).toBe("workflow_dispatch");
      expect(job?.repo).toBe("digithings-ai/digithings");
    }
    const archive = JOBS.find((job) => job.id === "twelve-x-archive-maintenance");
    expect(archive?.enabled).toBe(true);
    expect(archive?.inputs).toEqual({ dry_run: "false", dump_before_prune: "true" });
    for (const id of TWELVE_X_ENABLED_IDS) {
      const job = JOBS.find((row) => row.id === id);
      expect(job?.enabled).toBe(true);
      expect(job?.kind).toBe("workflow_dispatch");
      expect(job?.repo).toBe("digithings-ai/twelve-x");
    }
  });

  it("dispatches weekly twelve-x digisearch parity near Monday 09:00 UTC", () => {
    const job = JOBS.find((row) => row.id === "twelve-x-digisearch-parity");
    expect(job).toMatchObject({
      id: "twelve-x-digisearch-parity",
      cron: "8 9 * * MON",
      repo: "digithings-ai/twelve-x",
      kind: "workflow_dispatch",
      workflow: "digisearch_parity_check.yml",
      ref: "develop",
      enabled: true,
    });
    expect(job?.inputs).toBeUndefined();
    expect(jobsForCron("8 9 * * MON").map((row) => row.id)).toEqual([
      "twelve-x-digisearch-parity",
    ]);
    // Prior GHA was `0 9 * * 1`. Offset :08 avoids house-run-09 at 09:17.
    expect(jobsForCron("0 9 * * MON")).toEqual([]);
    expect(jobsForCron("17 9 * * MON").map((row) => row.id)).toEqual(["house-run-09"]);
  });
});
