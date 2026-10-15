/**
 * The lost-house-run watcher (DIG-3065).
 *
 * The load-bearing cases are the four verdicts `evaluateHouseRun` can return,
 * and the two directions the tick can fail without lying: an unreadable health
 * or run response must never become an alarm. Both are pinned here with no
 * network and no clock — `nowMs` and `deadlineSeconds` are injected, so the
 * "open past the deadline" case is an arithmetic fact rather than a timing race.
 */
import { describe, expect, it, vi } from "vitest";
import {
  alarmBody,
  alarmTitle,
  ALERT_REPO,
  checkHouseRuns,
  evaluateHouseRun,
  houseRunDeadlineSeconds,
  HOUSE_RUN_LOST_ERROR,
  HOUSE_RUN_WATCH_LABEL,
  readOpenRuns,
  readRun,
  runnerRunUrl,
  RUNNER_HEALTH_URL,
  RUN_WATCH_KEY,
  WATCHDOG_GRACE_SECONDS,
  type HouseRunObservation,
  type WatchFetch,
} from "./house-run-watch";

const NOW = Date.parse("2026-10-12T13:23:00.000Z");
/** house-run-09's timeout_seconds. The runner adds WATCHDOG_GRACE_SECONDS on top. */
const TIMEOUT = 14400;
const DEADLINE = TIMEOUT + WATCHDOG_GRACE_SECONDS;

/** A run started `ageSeconds` before NOW, in the shape publicRun() returns. */
function openRun(ageSeconds: number, extra: Partial<HouseRunObservation> = {}) {
  return {
    run_id: "run-lost",
    status: "running",
    started_at: new Date(NOW - ageSeconds * 1000).toISOString(),
    finished_at: null,
    ...extra,
  };
}

describe("evaluateHouseRun", () => {
  const evaluate = (observation: HouseRunObservation) =>
    evaluateHouseRun("run-lost", observation, { nowMs: NOW, deadlineSeconds: DEADLINE });

  it("raises a run the runner still holds open past timeout plus watchdog grace", () => {
    const verdict = evaluate(openRun(DEADLINE + 60));
    expect(verdict.lost).toBe(true);
    expect(verdict.reason).toBe("past-deadline");
    expect(verdict.age_seconds).toBe(DEADLINE + 60);
    expect(verdict.deadline_at).toBe(new Date(NOW - 60 * 1000).toISOString());
  });

  it("does not raise at the deadline itself — the runner is still entitled to its grace", () => {
    expect(evaluate(openRun(DEADLINE)).lost).toBe(false);
    expect(evaluate(openRun(DEADLINE)).reason).toBe("within-deadline");
  });

  it("does not raise a run still inside its deadline", () => {
    const verdict = evaluate(openRun(DEADLINE - 1));
    expect(verdict.lost).toBe(false);
    expect(verdict.reason).toBe("within-deadline");
  });

  it("raises on the runner's own house_run_lost, which needs no start time", () => {
    const verdict = evaluate({
      run_id: "run-lost",
      status: "failed",
      started_at: null,
      finished_at: null,
      error: HOUSE_RUN_LOST_ERROR,
    });
    expect(verdict.lost).toBe(true);
    expect(verdict.reason).toBe("runner-reported-lost");
    expect(verdict.age_seconds).toBeNull();
    expect(verdict.deadline_at).toBeNull();
  });

  it("never requires the house_run_lost field that PR #5488 adds", () => {
    // Every fixture above omits `error`. The field is read when present and
    // never required, so this watcher is correct before and after #5488 lands.
    // Asserted through the verdict, because HouseRunVerdict has no `error` field
    // at all — reading one would be true for the wrong reason.
    expect(evaluate(openRun(10))).toMatchObject({
      lost: false,
      reason: "within-deadline",
      started_at: new Date(NOW - 10_000).toISOString(),
    });
    // The same run one second past the deadline IS raised, so the arm above is
    // the absence of the field and not a verdict that never fires.
    expect(evaluate(openRun(DEADLINE + 1)).lost).toBe(true);
  });

  it("does not raise a terminal run however old it is", () => {
    for (const status of ["succeeded", "failed", "timed_out"]) {
      const verdict = evaluate(openRun(DEADLINE * 10, { status }));
      expect(verdict.lost, status).toBe(false);
      expect(verdict.reason, status).toBe("terminal");
    }
  });

  it("does not raise an unmeasurable run: a lock with no start time has no deadline", () => {
    const verdict = evaluate({ run_id: "run-lost", status: "running", started_at: null });
    expect(verdict.lost).toBe(false);
    expect(verdict.reason).toBe("no-start");
    expect(verdict.deadline_at).toBeNull();
  });

  it("does not raise on an unparseable start time", () => {
    const verdict = evaluate(openRun(0, { started_at: "not-a-date" }));
    expect(verdict.lost).toBe(false);
    expect(verdict.reason).toBe("no-start");
  });
});

describe("houseRunDeadlineSeconds", () => {
  it("adds the runner's watchdog grace to the declared timeout", () => {
    expect(houseRunDeadlineSeconds(TIMEOUT)).toBe(DEADLINE);
    expect(houseRunDeadlineSeconds(TIMEOUT)).toBe(14520);
  });
});

describe("reading the runner", () => {
  it("reads /healthz without an Authorization header", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({ ok: true, service: "digiquant-runner", git_sha: "abc", running: ["r1"] }),
    ) as unknown as WatchFetch;
    const result = await readOpenRuns(fetcher);
    expect(result).toEqual({ ok: true, running: ["r1"] });
    const [url, init] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(url).toBe(RUNNER_HEALTH_URL);
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer ");
  });

  it("treats an unhealthy runner as nothing-to-evaluate, not as zero open runs", async () => {
    const fetcher = vi.fn(async () => new Response("nope", { status: 500 })) as unknown as WatchFetch;
    expect(await readOpenRuns(fetcher)).toEqual({ ok: false, running: [] });
  });

  it("treats a health body without a running array as unreadable", async () => {
    const fetcher = vi.fn(async () => Response.json({ ok: true })) as unknown as WatchFetch;
    expect(await readOpenRuns(fetcher)).toEqual({ ok: false, running: [] });
  });

  it("reads a per-run record with the runner's bearer token", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({ run_id: "r1", status: "running", started_at: null }),
    ) as unknown as WatchFetch;
    const run = await readRun(fetcher, "r1", "runner-token");
    expect(run?.status).toBe("running");
    const [url, init] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(url).toBe(runnerRunUrl("r1"));
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer runner-token");
  });

  it("yields null — not a run — when the runner answers non-200", async () => {
    const fetcher = vi.fn(
      async () => Response.json({ error: "not_found" }, { status: 404 }),
    ) as unknown as WatchFetch;
    expect(await readRun(fetcher, "r1", "runner-token")).toBeNull();
  });
});

/**
 * A runner that routes by URL. A stub answering every path the same cannot tell
 * /healthz from /v1/jobs/<id>, so the per-run read would silently receive the
 * health body and every "lost" case would collapse to `no-start` — a green suite
 * proving nothing. Both routes must answer their own shape.
 */
function runnerFetch(opts: {
  running?: string[];
  run?: HouseRunObservation;
  healthStatus?: number;
  runStatus?: number;
}): WatchFetch {
  return (async (url: string) => {
    if (url.includes("/healthz")) {
      if (opts.healthStatus && opts.healthStatus !== 200) {
        return new Response("down", { status: opts.healthStatus });
      }
      return Response.json({ ok: true, running: opts.running ?? [] });
    }
    if (opts.runStatus && opts.runStatus !== 200) {
      return new Response("Unauthorized", { status: opts.runStatus });
    }
    return Response.json(opts.run ?? {});
  }) as unknown as WatchFetch;
}

describe("the alarm", () => {
  const lost = evaluateHouseRun("run-lost", openRun(DEADLINE + 60), {
    nowMs: NOW,
    deadlineSeconds: DEADLINE,
  });
  const verdict_started_at = (v: { started_at: string | null }) => v.started_at ?? "";

  it("titles the occurrence by run id, so a repeat dedupes and a new run does not", () => {
    expect(alarmTitle(lost)).toBe("digiquant house-run run-lost did not land");
    expect(
      alarmTitle({ ...lost, run_id: "run-other", reason: "runner-reported-lost" }),
    ).not.toBe(alarmTitle(lost));
  });

  it("carries the run-watch key and the read-only promise in the body", () => {
    const body = alarmBody(lost, DEADLINE);
    expect(body).toContain(RUN_WATCH_KEY);
    expect(body).toContain("read-only");
    expect(body).toContain(String(DEADLINE));
    expect(body).toContain(verdict_started_at(lost));
  });

  it("files into digithings with a class label, one issue per occurrence", async () => {
    const seen: { url: string; method: string; body?: string }[] = [];
    const github: WatchFetch = vi.fn(async (url: string, init: RequestInit) => {
      seen.push({ url, method: String(init.method), body: init.body ? String(init.body) : undefined });
      if (url.includes("/issues?")) return Response.json([]);
      if (url.includes("/labels/")) return Response.json({ name: HOUSE_RUN_WATCH_LABEL });
      return Response.json({ html_url: "https://github.com/x/y/issues/1" }, { status: 201 });
    }) as unknown as WatchFetch;

    const result = await checkHouseRuns({
      fetchRunner: runnerFetch({ running: ["run-lost"], run: openRun(DEADLINE + 60) }),
      fetchGithub: github,
      runnerToken: "runner-token",
      githubToken: "github-token",
      timeoutSeconds: TIMEOUT,
      nowMs: NOW,
    });

    expect(result.ok).toBe(true);
    expect(result.open).toBe(1);
    expect(result.lost.map((v) => v.reason)).toEqual(["past-deadline"]);
    expect(result.raised).toEqual([
      { run_id: "run-lost", raised: true, url: "https://github.com/x/y/issues/1" },
    ]);
    const created = seen.filter((call) => call.method === "POST" && call.body);
    expect(created).toHaveLength(1);
    expect(created[0].url).toBe(`https://api.github.com/repos/${ALERT_REPO}/issues`);
    const payload = JSON.parse(created[0].body as string) as Record<string, unknown>;
    expect(payload.labels).toEqual([HOUSE_RUN_WATCH_LABEL]);
    expect(payload.title).toBe(alarmTitle(lost));
  });

  it("does not re-file an occurrence it can already see open", async () => {
    const posts: string[] = [];
    const github: WatchFetch = vi.fn(async (url: string, init: RequestInit) => {
      if (init.method === "POST") posts.push(url);
      if (url.includes("/issues?")) {
        return Response.json([{ title: alarmTitle(lost), html_url: "https://gh/9" }]);
      }
      if (url.includes("/labels/")) return Response.json({ name: HOUSE_RUN_WATCH_LABEL });
      return Response.json({}, { status: 201 });
    }) as unknown as WatchFetch;

    const result = await checkHouseRuns({
      fetchRunner: runnerFetch({ running: ["run-lost"], run: openRun(DEADLINE + 60) }),
      fetchGithub: github,
      runnerToken: "runner-token",
      githubToken: "github-token",
      timeoutSeconds: TIMEOUT,
      nowMs: NOW,
    });

    expect(posts).toHaveLength(0);
    expect(result.raised).toEqual([{ run_id: "run-lost", raised: false, url: "https://gh/9" }]);
  });

  it("raises anyway when it could not read the open occurrences — never dedupes blind", async () => {
    const posts: string[] = [];
    const github: WatchFetch = vi.fn(async (url: string, init: RequestInit) => {
      if (init.method === "POST") posts.push(url);
      if (url.includes("/issues?")) return new Response("boom", { status: 500 });
      if (url.includes("/labels/")) return new Response("boom", { status: 500 });
      return Response.json({ html_url: "https://gh/10" }, { status: 201 });
    }) as unknown as WatchFetch;

    const result = await checkHouseRuns({
      fetchRunner: runnerFetch({ running: ["run-lost"], run: openRun(DEADLINE + 60) }),
      fetchGithub: github,
      runnerToken: "runner-token",
      githubToken: "github-token",
      timeoutSeconds: TIMEOUT,
      nowMs: NOW,
    });

    expect(posts).toHaveLength(1);
    expect(result.raised[0].raised).toBe(true);
  });

  it("never throws when GitHub is down", async () => {
    const github: WatchFetch = vi.fn(async () => {
      throw new Error("network down");
    }) as unknown as WatchFetch;
    const result = await checkHouseRuns({
      fetchRunner: runnerFetch({ running: ["run-lost"], run: openRun(DEADLINE + 60) }),
      fetchGithub: github,
      runnerToken: "runner-token",
      githubToken: "github-token",
      timeoutSeconds: TIMEOUT,
      nowMs: NOW,
    });
    expect(result.lost).toHaveLength(1);
    expect(result.raised).toEqual([{ run_id: "run-lost", raised: false }]);
  });
});

describe("a tick that cannot see anything raises nothing", () => {
  const lost = { ok: true, running: ["run-lost"] };

  it("raises nothing when /healthz is unreadable", async () => {
    const github: WatchFetch = vi.fn(async () => Response.json({}, { status: 201 })) as unknown as WatchFetch;
    const result = await checkHouseRuns({
      fetchRunner: (async () => new Response("down", { status: 503 })) as unknown as WatchFetch,
      fetchGithub: github,
      runnerToken: "runner-token",
      githubToken: "github-token",
      timeoutSeconds: TIMEOUT,
      nowMs: NOW,
    });
    expect(result.ok).toBe(false);
    expect(result.lost).toEqual([]);
    expect(result.open).toBe(0);
    expect(github).not.toHaveBeenCalled();
  });

  it("raises nothing when the per-run read fails, even though the lock is held", async () => {
    const github: WatchFetch = vi.fn(async () => Response.json({}, { status: 201 })) as unknown as WatchFetch;
    const result = await checkHouseRuns({
      fetchRunner: (async (url: string) =>
        url.includes("/healthz")
          ? Response.json(lost)
          : new Response("Unauthorized", { status: 401 })) as unknown as WatchFetch,
      fetchGithub: github,
      runnerToken: "",
      githubToken: "github-token",
      timeoutSeconds: TIMEOUT,
      nowMs: NOW,
    });
    expect(result.ok).toBe(true);
    expect(result.open).toBe(1);
    expect(result.unreadable).toEqual(["run-lost"]);
    expect(result.lost).toEqual([]);
    expect(github).not.toHaveBeenCalled();
  });

  it("raises nothing when the runner reports no open runs at all", async () => {
    const github: WatchFetch = vi.fn(async () => Response.json({}, { status: 201 })) as unknown as WatchFetch;
    const result = await checkHouseRuns({
      fetchRunner: (async () => Response.json({ ok: true, running: [] })) as unknown as WatchFetch,
      fetchGithub: github,
      runnerToken: "runner-token",
      githubToken: "github-token",
      timeoutSeconds: TIMEOUT,
      nowMs: NOW,
    });
    expect(result).toMatchObject({ ok: true, open: 0, lost: [], unreadable: [], raised: [] });
  });
});
describe("the never-dispatched arm (DIG-3456)", () => {
  const MONDAY_0917 = Date.parse("2026-10-12T09:17:00.000Z");
  const PAST_DEADLINE = MONDAY_0917 + (TIMEOUT + WATCHDOG_GRACE_SECONDS) * 1000 + 60_000;

  it("names the most recent Monday as the expected run_date", async () => {
    const mod = await import("./house-run-watch");
    expect(mod.lastMondayRunDate(Date.parse("2026-10-12T00:01:00.000Z"))).toBe("2026-10-12");
    expect(mod.lastMondayRunDate(Date.parse("2026-10-12T13:23:00.000Z"))).toBe("2026-10-12");
    expect(mod.lastMondayRunDate(Date.parse("2026-10-11T23:59:00.000Z"))).toBe("2026-10-05");
    expect(mod.lastMondayRunDate(Date.parse("2026-10-13T00:00:00.000Z"))).toBe("2026-10-12");
    expect(mod.lastMondayRunDate(Date.parse("2026-10-14T12:00:00.000Z"))).toBe("2026-10-12");
  });

  it("stays quiet before Monday 09:17 plus the deadline, however empty the runner", async () => {
    const mod = await import("./house-run-watch");
    const verdict = mod.evaluateNeverDispatched(
      "2026-10-12",
      { nowMs: Date.parse("2026-10-12T10:00:00.000Z"), deadlineSeconds: TIMEOUT + WATCHDOG_GRACE_SECONDS },
      { run_date: "2026-10-12", landed: false, open_house_runs: [], verifiable: true },
    );
    expect(verdict).toEqual({ run_date: "2026-10-12", lost: false, reason: "not-due" });
  });

  it("stays quiet when the marker landed", async () => {
    const mod = await import("./house-run-watch");
    const verdict = mod.evaluateNeverDispatched(
      "2026-10-12",
      { nowMs: PAST_DEADLINE, deadlineSeconds: TIMEOUT + WATCHDOG_GRACE_SECONDS },
      { run_date: "2026-10-12", landed: true, open_house_runs: [], verifiable: true },
    );
    expect(verdict).toEqual({ run_date: "2026-10-12", lost: false, reason: "landed" });
  });

  it("leaves an open house run to the past-deadline arm, which reads the run itself", async () => {
    const mod = await import("./house-run-watch");
    const verdict = mod.evaluateNeverDispatched(
      "2026-10-12",
      { nowMs: PAST_DEADLINE, deadlineSeconds: TIMEOUT + WATCHDOG_GRACE_SECONDS },
      { run_date: "2026-10-12", landed: false, open_house_runs: ["run-still-open"], verifiable: true },
    );
    expect(verdict).toEqual({ run_date: "2026-10-12", lost: false, reason: "open-house-run" });
  });

  it("never raises on a landing read it could not verify", async () => {
    const mod = await import("./house-run-watch");
    for (const status of [null, { run_date: "2026-10-12", landed: false, open_house_runs: [], verifiable: false }]) {
      const verdict = mod.evaluateNeverDispatched(
        "2026-10-12",
        { nowMs: PAST_DEADLINE, deadlineSeconds: TIMEOUT + WATCHDOG_GRACE_SECONDS },
        status,
      );
      expect(verdict, JSON.stringify(status)).toEqual({
        run_date: "2026-10-12",
        lost: false,
        reason: "unverifiable",
      });
    }
  });

  it("fires past the deadline with a verified absent marker and no open run", async () => {
    const mod = await import("./house-run-watch");
    const verdict = mod.evaluateNeverDispatched(
      "2026-10-12",
      { nowMs: PAST_DEADLINE, deadlineSeconds: TIMEOUT + WATCHDOG_GRACE_SECONDS },
      { run_date: "2026-10-12", landed: false, open_house_runs: [], verifiable: true },
    );
    expect(verdict).toEqual({ run_date: "2026-10-12", lost: true, reason: "never-dispatched" });
  });

  it("rejects a misrouted body instead of reading it as a missing Monday", async () => {
    const mod = await import("./house-run-watch");
    // A health body answers 200 with no landed field; the strict shape check
    // must yield null so the tick stays quiet rather than alarming.
    const fetcher = (async () => Response.json({ ok: true, running: [] })) as unknown as WatchFetch;
    expect(await mod.readHouseStatus(fetcher, "2026-10-12", "runner-token")).toBeNull();
    const html = (async () => Response.json({ run_date: "2026-10-05", landed: true, open_house_runs: [], verifiable: true })) as unknown as WatchFetch;
    expect(await mod.readHouseStatus(html, "2026-10-12", "runner-token")).toBeNull();
  });

  it("reads the landing with the runner bearer token", async () => {
    const mod = await import("./house-run-watch");
    const fetcher = vi.fn(async () =>
      Response.json({ run_date: "2026-10-12", landed: true, open_house_runs: [], verifiable: true }),
    ) as unknown as WatchFetch;
    const status = await mod.readHouseStatus(fetcher, "2026-10-12", "runner-token");
    expect(status).toEqual({ run_date: "2026-10-12", landed: true, open_house_runs: [], verifiable: true });
    const [url, init] = (fetcher as unknown as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://digiquant-runner/v1/jobs/house-status?run_date=2026-10-12");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer runner-token");
  });

  it("raises one dated issue for a Monday with no landing and no open run", async () => {
    const mod = await import("./house-run-watch");
    const posts: { url: string; body?: string }[] = [];
    const github: WatchFetch = vi.fn(async (url: string, init: RequestInit) => {
      if (init.method === "POST") posts.push({ url, body: init.body ? String(init.body) : undefined });
      if (url.includes("/issues?")) return Response.json([]);
      if (url.includes("/labels/")) return Response.json({ name: HOUSE_RUN_WATCH_LABEL });
      return Response.json({ html_url: "https://github.com/x/y/issues/2" }, { status: 201 });
    }) as unknown as WatchFetch;
    const fetchRunner = (async (url: string) => {
      if (url.includes("/healthz")) return Response.json({ ok: true, running: [] });
      return Response.json({ run_date: "2026-10-12", landed: false, open_house_runs: [], verifiable: true });
    }) as unknown as WatchFetch;
    const result = await checkHouseRuns({
      fetchRunner,
      fetchGithub: github,
      runnerToken: "runner-token",
      githubToken: "github-token",
      timeoutSeconds: TIMEOUT,
      nowMs: PAST_DEADLINE,
    });
    expect(result.ok).toBe(true);
    expect(result.neverDispatched).toEqual([{ run_date: "2026-10-12", lost: true, reason: "never-dispatched" }]);
    expect(result.raised).toEqual([{ run_id: "house-run:2026-10-12", raised: true, url: "https://github.com/x/y/issues/2" }]);
    const created = posts.filter((call) => call.url.endsWith("/issues"));
    expect(created).toHaveLength(1);
    const payload = JSON.parse(created[0].body as string) as Record<string, unknown>;
    expect(payload.title).toBe(mod.neverDispatchedTitle("2026-10-12"));
    expect(payload.labels).toEqual([HOUSE_RUN_WATCH_LABEL]);
  });

  it("does not re-file a Monday occurrence it can already see open", async () => {
    const mod = await import("./house-run-watch");
    const posts: string[] = [];
    const github: WatchFetch = vi.fn(async (url: string, init: RequestInit) => {
      if (init.method === "POST") posts.push(url);
      if (url.includes("/issues?")) {
        return Response.json([{ title: mod.neverDispatchedTitle("2026-10-12"), html_url: "https://gh/11" }]);
      }
      if (url.includes("/labels/")) return Response.json({ name: HOUSE_RUN_WATCH_LABEL });
      return Response.json({}, { status: 201 });
    }) as unknown as WatchFetch;
    const fetchRunner = (async (url: string) => {
      if (url.includes("/healthz")) return Response.json({ ok: true, running: [] });
      return Response.json({ run_date: "2026-10-12", landed: false, open_house_runs: [], verifiable: true });
    }) as unknown as WatchFetch;
    const result = await checkHouseRuns({
      fetchRunner,
      fetchGithub: github,
      runnerToken: "runner-token",
      githubToken: "github-token",
      timeoutSeconds: TIMEOUT,
      nowMs: PAST_DEADLINE,
    });
    expect(posts).toHaveLength(0);
    expect(result.raised).toEqual([{ run_id: "house-run:2026-10-12", raised: false, url: "https://gh/11" }]);
  });
});
