/**
 * digithings-cron — org-wide Cloudflare Worker production clocks (#3579, #4761).
 * Cron Triggers fire workflow_dispatch / repository_dispatch, POST the
 * private digiquant-runner when the job kind is "container", or fetch public
 * probe URLs when the job kind is "probe".
 * scheduled() returns in seconds: waitUntil covers the POST and does not
 * await the container job.
 */
import { buildPlan } from "./backfill";
import { BackfillLedger, type RemediationState } from "./backfill-do";
import { dispatch, dispatchWorkflow, type DispatchResult } from "./dispatch";
import type { Env } from "./env";
import { shouldDispatchAtOpen } from "./et-open";
import { jobsForCron, type Job } from "./jobs";

/**
 * Wrangler.toml binds BACKFILL_LEDGER to class BackfillLedger, and a DO class
 * only exists in a deployment if the entrypoint exports it as a value. A
 * type-only import satisfies tsc and satisfies nothing at deploy time:
 * `wrangler deploy` fails with "not exported in your entrypoint file", which no
 * test or typecheck in CI sees.
 */
export { BackfillLedger };

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

  /**
   * The ledger's per-date state, read at response time so it describes what
   * actually settled rather than what was claimed. Without it a caller cannot
   * tell "nothing to do" from "stranded by a dead request" — `dispatched: []`
   * and `already_remediated: true` looked identical either way.
   *
   * The read is guarded because it hits the same Durable Object that may be the
   * thing failing: losing `states` is a far smaller harm than letting it replace
   * the status the caller needs with an unhandled 500.
   */
  const readStates = async (): Promise<Record<string, RemediationState | "unknown"> | undefined> => {
    try {
      return await stub.status(plan.dates);
    } catch (err) {
      console.error(
        JSON.stringify({
          cron: "backfill",
          job: BACKFILL_LEDGER_NAME,
          error: "ledger_read_failed",
          detail: err instanceof Error ? err.message : String(err),
        }),
      );
      return undefined;
    }
  };

  const respond = (
    body: Record<string, unknown>,
    status: number,
    states: Record<string, RemediationState | "unknown"> | undefined,
  ) => Response.json(states ? { ...body, states } : body, { status });

  if (split.toDispatch.length === 0) {
    // Every date is claimed by a live request or already remediated. This is the
    // idempotence guarantee: a repeat dispatch is a no-op, not a second write.
    const states = await readStates();
    return respond(
      {
        ok: true,
        dispatched: [],
        skipped: split.skipped,
        // `done` is the only state that means remediated. A date held by a live
        // request is somebody else's turn, not a finished backfill, and calling
        // it remediated is the false report this field used to make.
        already_remediated: states
          ? plan.dates.every((date) => states[date] === "done")
          : false,
      },
      200,
      states,
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
      const release_failed = !(await writeLedger("release", () => stub.release(split.toDispatch)));
      return respond(
        {
          ok: true,
          dry_run: true,
          dispatched: [],
          skipped: split.skipped,
          would_dispatch: split.toDispatch,
          release_failed,
        },
        200,
        await readStates(),
      );
    }

    if (result.status === 422) {
      // GitHub declined to start a run — the maintenance workflow is disabled, or
      // a run for this ref is already queued. No run exists for these dates, so
      // this is NOT remediation: recording `done` is what let a later retry answer
      // "already remediated" for a date that was never backfilled, forever. The
      // dates settle as `dispatch_suppressed`, stay claimable for the next POST,
      // and the caller gets 409 — not the 200 that claimed success.
      const ledger_write_failed = !(
        await writeLedger("markSuppressed", () =>
          stub.markSuppressed(split.toDispatch, now, result.status),
        )
      );
      return respond(
        {
          error: "dispatch_suppressed",
          detail: "GitHub started no run for these dates; they stay dispatchable",
          dispatched: [],
          skipped: split.skipped,
          github_status: result.status,
          ledger_write_failed,
        },
        409,
        await readStates(),
      );
    }

    // GitHub accepted (204/200), so a run exists for these dates whatever this
    // Worker does next. The ledger write is therefore not allowed to undo that:
    // releasing here would re-dispatch dates that already ran — the DIG-48
    // surplus — and answering 502 would report a GitHub success as a failure. If
    // the write fails the claim stays `in_flight` and ages out via
    // IN_FLIGHT_TTL_MS, which is the honest outcome: at most one extra dispatch,
    // and the caller is told the ledger is behind.
    const ledger_write_failed = !(
      await writeLedger("markDone", () => stub.markDone(split.toDispatch, now))
    );
    return respond(
      {
        ok: true,
        dispatched: split.toDispatch,
        skipped: split.skipped,
        github_status: result.status,
        ledger_write_failed,
      },
      200,
      await readStates(),
    );
  } catch (err) {
    // A genuine dispatch failure: nothing ran upstream, so the claim goes back
    // for the next request. If the release itself throws, the claim is left
    // in_flight and ages out via IN_FLIGHT_TTL_MS rather than staying locked
    // forever — which is why the failure is reported instead of swallowed, and
    // why the status stays 502 rather than becoming an unhandled 500.
    const release_failed = !(await writeLedger("release", () => stub.release(split.toDispatch)));
    const detail = err instanceof Error ? err.message : String(err);
    return respond({ error: "dispatch_failed", detail, release_failed }, 502, await readStates());
  }
}

/**
 * Run one ledger write and report whether it landed, instead of letting it
 * throw. Each caller decides what a failure means — for `markDone` it must not
 * undo an accepted dispatch, for `release` it must not replace a 502 with a 500
 * — so the write is never silently retried and never silently swallowed: the
 * caller-facing flag plus one log line naming the write is the record.
 */
async function writeLedger(op: "markDone" | "markSuppressed" | "release", write: () => Promise<void>) {
  try {
    await write();
    return true;
  } catch (err) {
    console.error(
      JSON.stringify({
        cron: "backfill",
        job: BACKFILL_LEDGER_NAME,
        error: "ledger_write_failed",
        op,
        detail: err instanceof Error ? err.message : String(err),
      }),
    );
    return false;
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
