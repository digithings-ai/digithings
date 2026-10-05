/**
 * digithings-cron — org-wide Cloudflare Worker production clocks (#3579, #4761).
 * Cron Triggers fire workflow_dispatch / repository_dispatch, POST the
 * private digiquant-runner when the job kind is "container", or fetch public
 * probe URLs when the job kind is "probe".
 * scheduled() returns in seconds: waitUntil covers the POST and does not
 * await the container job.
 */
import { buildPlan } from "./backfill";
import type { BackfillLedger } from "./backfill-do";
import { dispatch, dispatchWorkflow, type DispatchResult } from "./dispatch";
import type { Env } from "./env";
import { shouldDispatchAtOpen } from "./et-open";
import { jobsForCron, type Job } from "./jobs";

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
    console.error(JSON.stringify({ cron, error: "unmapped_cron" }));
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

/** Upstream twelve-x workflow this dispatches. Not a daily_run.yml `run_date`. */
const BACKFILL_REPO = "digithings-ai/twelve-x";
const BACKFILL_WORKFLOW = "maintenance.yml";
const BACKFILL_REF = "develop";
const BACKFILL_LEDGER_NAME = "backfill-ledger";

/**
 * POST /backfill — the Cloudflare-native dispatch surface for dated snapshot
 * backfills (DIG-55 rework, DIG-753).
 *
 * Deliberately not a JOBS row and therefore not a clock: there is no cron, no
 * `enabled` flag on a row, and nothing in wrangler.toml's [triggers] lists it.
 * The only way a backfill starts is a request that names its dates.
 *
 * Ladder, all before the first outbound request: secret unset -> 404, bad
 * bearer -> 401, BACKFILL_ENABLED != "1" -> 404, then buildPlan() refusals, then
 * the ledger partition. A dispatch whose dates are all already remediated makes
 * zero upstream requests and answers 200.
 */
async function handleBackfill(request: Request, env: Env): Promise<Response> {
  if (!env.CRON_KICK_SECRET) {
    return new Response("Not Found", { status: 404 });
  }
  if (!authorized(request, env)) {
    return new Response("Unauthorized", { status: 401 });
  }
  if (env.BACKFILL_ENABLED !== "1") {
    return Response.json(
      { error: "backfill_disabled", detail: "set BACKFILL_ENABLED=1 to enable" },
      { status: 404 },
    );
  }

  const plan = buildPlan(await request.text());
  if (!plan.ok) {
    return Response.json({ error: plan.code, detail: plan.detail }, { status: 400 });
  }

  if (!env.BACKFILL_LEDGER) {
    return Response.json({ error: "backfill_unconfigured" }, { status: 503 });
  }

  const stub = env.BACKFILL_LEDGER.get(
    env.BACKFILL_LEDGER.idFromName(BACKFILL_LEDGER_NAME),
  ) as unknown as BackfillLedger;
  const now = new Date().toISOString();

  const split = await stub.claim(plan.dates, now, plan.force_dates);
  if (split.toDispatch.length === 0) {
    // Every date is already claimed or remediated. This is the idempotence
    // guarantee: a repeat dispatch is a no-op, not a second write.
    return Response.json(
      { ok: true, dispatched: [], skipped: split.skipped, already_remediated: true },
      { status: 200 },
    );
  }

  try {
    const result = await dispatchWorkflow(env, {
      cron: "backfill",
      label: BACKFILL_LEDGER_NAME,
      repo: BACKFILL_REPO,
      workflow: BACKFILL_WORKFLOW,
      ref: BACKFILL_REF,
      inputs: {
        backfill_snapshots: "true",
        dates: split.toDispatch.join(","),
      },
    });

    if (result.dry_run) {
      // Nothing ran upstream, so nothing may be recorded as remediated.
      await stub.release(split.toDispatch);
      return Response.json(
        { ok: true, dry_run: true, dispatched: [], skipped: split.skipped, would_dispatch: split.toDispatch },
        { status: 200 },
      );
    }

    await stub.markDone(split.toDispatch, now);
    return Response.json(
      {
        ok: true,
        dispatched: split.toDispatch,
        skipped: split.skipped,
        github_status: result.status,
      },
      { status: 200 },
    );
  } catch (err) {
    // Release the claim so the same dates can be retried by the next request.
    await stub.release(split.toDispatch);
    const detail = err instanceof Error ? err.message : String(err);
    return Response.json({ error: "dispatch_failed", detail }, { status: 502 });
  }
}

export default {
  async scheduled(
    controller: ScheduledController,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<void> {
    await runJobsForCron(controller.cron, controller.scheduledTime, env, ctx);
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

    if (request.method === "POST" && path === "/backfill") {
      return handleBackfill(request, env);
    }

    return new Response("Not Found", { status: 404 });
  },
};

export type { Env, Job };
