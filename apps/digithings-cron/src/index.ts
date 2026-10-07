/**
 * digithings-cron — org-wide Cloudflare Worker production clocks (#3579, #4761).
 * Cron Triggers fire workflow_dispatch / repository_dispatch, POST the
 * private digiquant-runner when the job kind is "container", or fetch public
 * probe URLs when the job kind is "probe".
 * scheduled() returns in seconds: waitUntil covers the POST and does not
 * await the container job.
 *
 * A cron that fires with no enabled job behind it raises an alarm on the
 * twelve-x issues path (DIG-732). Which class it raises is derived from the
 * required-trigger contract, not decided here: a required cron firing with no
 * backstop is missing_required_cron, anything else is unrecognised_cron. The
 * required set itself is `src/required-triggers.ts` and is also checked against
 * the deployed trigger list, not only against wrangler.toml.
 */
import { dispatch, type DispatchResult } from "./dispatch";
import type { Env } from "./env";
import { shouldDispatchAtOpen } from "./et-open";
import { jobsForCron, type Job } from "./jobs";
import { raiseViolationAlarms } from "./trigger-alarm";
import { violationsForTick } from "./trigger-contract";

export type StartedRun = {
  job_id: string;
  status: string;
  run_id?: string;
};

type RunOptions = {
  /** Skip etOpenGate and preserve privileged house args for this kick only. */
  force?: boolean;
  /** Optional kick args (for example run_writers=true). Cron sends none. */
  args?: Record<string, string>;
  /** POST /kick awaits so the response can include run ids. */
  awaitDispatch?: boolean;
  /** Manual /kick may start paused jobs; scheduled() never sets this. */
  includeDisabled?: boolean;
  /**
   * A cron tick with no job behind it is deployment drift, so it alarms.
   * POST /kick leaves this off: a human typing a cron by hand is not drift.
   */
  alarmUnmapped?: boolean;
};

export function houseArgs(
  force: boolean,
  bodyArgs: Record<string, string>,
  now: number,
): Record<string, string> {
  const runDate = new Date(now).toISOString().slice(0, 10);
  if (!force) {
    return { refresh_scope: "none", run_date: runDate };
  }
  return {
    ...bodyArgs,
    refresh_scope: bodyArgs.refresh_scope ?? "none",
    run_date: bodyArgs.run_date ?? runDate,
    force: "true",
  };
}

/** Ordinary ticks and unforced kicks send {}. Only force may keep dry_run "true". */
export function checkpointArgs(
  force: boolean,
  bodyArgs: Record<string, string>,
): Record<string, string> {
  if (force && bodyArgs.dry_run === "true") {
    return { dry_run: "true" };
  }
  return {};
}

function startedRun(job: Job, result: DispatchResult): StartedRun {
  const run: StartedRun = {
    job_id: job.id,
    status: result.container_status ?? (result.dry_run ? "dry_run" : "dispatched"),
  };
  if (result.run_id) run.run_id = result.run_id;
  return run;
}

async function runJobsForCron(
  cron: string,
  scheduledTime: number,
  env: Env,
  ctx: ExecutionContext,
  opts: RunOptions = {},
): Promise<{ started: string[]; skipped: string[]; runs: StartedRun[] }> {
  const jobs = jobsForCron(cron, { includeDisabled: opts.includeDisabled });
  const started: string[] = [];
  const skipped: string[] = [];
  const pending: Promise<StartedRun>[] = [];

  if (jobs.length === 0) {
    // The class is derived, never hardcoded: the tick asks the contract what
    // this cron breaking means. Hardcoding "unrecognised" made a disabled
    // required row — a lost backstop — report as silence, which is the failure
    // DIG-732 exists to prevent.
    const violations = violationsForTick(cron);
    const class: string = violations[0]?.class ?? "none";
    // Still one line per occurrence for observability search, now carrying the
    // class. Before DIG-732 this was the whole response to a trigger that fires
    // with nothing behind it.
    console.error(JSON.stringify({ cron, error: "unmapped_cron", alarm_class: class }));
    // A parked cron (only disabled rows claim it — `house-run-10/11/12` keep
    // their cron lines as retry slots) is a known configuration, not drift, and
    // violationsForTick returns nothing for it.
    if (opts.alarmUnmapped && violations.length > 0) {
      // waitUntil, not await: the tick has nothing to dispatch, and the alarm
      // must not become a reason for scheduled() to throw.
      ctx.waitUntil(
        raiseViolationAlarms(
          env,
          violations,
          "the deployed trigger list, at the tick that fired",
        ),
      );
    }
  }
  for (const job of jobs) {
    if (job.etOpenGate && !opts.force && !shouldDispatchAtOpen(cron, scheduledTime)) {
      skipped.push(job.id);
      console.log(
        JSON.stringify({
          cron,
          repo: job.repo,
          job: job.id,
          github_status: null,
          dry_run: env.DRY_RUN === "1",
          skipped: "et_open_gate",
        }),
      );
      continue;
    }
    started.push(job.id);
    let args = opts.args;
    if (job.command === "house-run") {
      args = houseArgs(opts.force === true, opts.args ?? {}, scheduledTime);
    } else if (job.command === "checkpoint-archive") {
      args = checkpointArgs(opts.force === true, opts.args ?? {});
    }
    pending.push(
      dispatch(env, job, cron, scheduledTime, { args }).then((result) =>
        startedRun(job, result),
      ).catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        console.error(JSON.stringify({ cron, job: job.id, error: msg }));
        throw err;
      }),
    );
  }
  if (pending.length === 0) {
    return { started, skipped, runs: [] };
  }
  if (opts.awaitDispatch) {
    const runs = await Promise.all(pending);
    return { started, skipped, runs };
  }
  ctx.waitUntil(Promise.all(pending));
  return { started, skipped, runs: [] };
}

function normalizePath(pathname: string): string {
  if (pathname.length > 1 && pathname.endsWith("/")) {
    return pathname.slice(0, -1);
  }
  return pathname || "/";
}

function authorized(request: Request, env: Env): boolean {
  const expected = `Bearer ${env.CRON_KICK_SECRET}`;
  return (request.headers.get("Authorization") ?? "") === expected;
}

function parseStringArgs(value: unknown): Record<string, string> | null {
  if (value === undefined) return {};
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const out: Record<string, string> = {};
  for (const [key, item] of Object.entries(value)) {
    if (typeof item !== "string") return null;
    out[key] = item;
  }
  return out;
}

export default {
  async scheduled(
    controller: ScheduledController,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<void> {
    await runJobsForCron(controller.cron, controller.scheduledTime, env, ctx, {
      alarmUnmapped: true,
    });
  },

  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const path = normalizePath(url.pathname);

    if (request.method === "GET" && (path === "/" || path === "/healthz")) {
      return Response.json(
        {
          ok: true,
          service: "digithings-cron",
          dry_run: env.DRY_RUN === "1",
        },
        { status: 200 },
      );
    }

    if (request.method === "GET" && path.startsWith("/runs/")) {
      if (!env.CRON_KICK_SECRET) {
        return new Response("Not Found", { status: 404 });
      }
      if (!authorized(request, env)) {
        return new Response("Unauthorized", { status: 401 });
      }
      const runId = decodeURIComponent(path.slice("/runs/".length));
      if (!runId || runId.includes("/")) {
        return new Response("Not Found", { status: 404 });
      }
      if (!env.RUNNER || !env.RUNNER_AUTH_TOKEN) {
        return Response.json({ error: "runner_unconfigured" }, { status: 503 });
      }
      return env.RUNNER.fetch(
        `https://digiquant-runner/v1/jobs/${encodeURIComponent(runId)}`,
        {
          method: "GET",
          headers: { Authorization: `Bearer ${env.RUNNER_AUTH_TOKEN}` },
        },
      );
    }

    if (request.method === "POST" && path === "/kick") {
      if (!env.CRON_KICK_SECRET) {
        return new Response("Not Found", { status: 404 });
      }
      if (!authorized(request, env)) {
        return new Response("Unauthorized", { status: 401 });
      }
      let cron = "";
      let force = false;
      let args: Record<string, string> = {};
      try {
        const body = (await request.json()) as {
          cron?: unknown;
          force?: unknown;
          args?: unknown;
        };
        cron = typeof body.cron === "string" ? body.cron : "";
        force = body.force === true;
        const parsedArgs = parseStringArgs(body.args);
        if (parsedArgs === null) {
          return Response.json({ error: "invalid_args" }, { status: 400 });
        }
        args = parsedArgs;
      } catch {
        return Response.json({ error: "invalid_json" }, { status: 400 });
      }
      if (!cron) {
        return Response.json({ error: "cron_required" }, { status: 400 });
      }
      const result = await runJobsForCron(cron, Date.now(), env, ctx, {
        force,
        args,
        awaitDispatch: true,
        includeDisabled: true,
      });
      return Response.json({ ok: true, cron, ...result }, { status: 200 });
    }

    return new Response("Not Found", { status: 404 });
  },
};

export type { Env, Job };
