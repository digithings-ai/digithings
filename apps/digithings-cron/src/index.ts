/**
 * digithings-cron — org-wide Cloudflare Worker production clocks (#3579, #4761).
 * Cron Triggers fire workflow_dispatch / repository_dispatch, POST the
 * private digiquant-runner when the job kind is "container", or fetch public
 * probe URLs when the job kind is "probe".
 * scheduled() returns in seconds: waitUntil covers the POST and does not
 * await the container job.
 *
 * A cron that fires with no job row behind it raises an alarm on the
 * twelve-x issues path (DIG-732): unrecognised_cron, which is a different class
 * from a required cron being absent. The required set itself is
 * `src/required-triggers.ts` and is checked against the deployed trigger list,
 * not only against wrangler.toml. A cron whose only owner is a deliberately
 * disabled job is a known retry slot, not drift, so it stays silent.
 */
import { buildPlan } from "./backfill";
import { BackfillLedger, type RemediationState } from "./backfill-do";
import { StartCounter } from "./counter-do";
import { dispatch, dispatchWorkflow, type DispatchResult, UNDECLARED_INPUT } from "./dispatch";
import type { Env } from "./env";
import { shouldDispatchAtOpen } from "./et-open";
import { jobsForCron, type Job } from "./jobs";
import { raiseViolationAlarms } from "./trigger-alarm";
import { unrecognisedCronViolation } from "./trigger-contract";

/**
 * Wrangler.toml binds BACKFILL_LEDGER to class BackfillLedger, and a DO class
 * only exists in a deployment if the entrypoint exports it as a value. A
 * type-only import satisfies tsc and satisfies nothing at deploy time:
 * `wrangler deploy` fails with "not exported in your entrypoint file", which no
 * test or typecheck in CI sees. START_COUNTER is the same contract.
 */
export { BackfillLedger, StartCounter };

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
  /**
   * Claim each job's cron slot before dispatching. Only scheduled() sets this.
   *
   * Cloudflare delivers a Cron Trigger at least once: on 14-17 Oct 2026 every
   * tick of this Worker arrived twice, 7-29s apart, and each copy dispatched.
   * A second delivery of the same slot must not start a second run. /kick never
   * claims, because a human may legitimately kick the same cron twice.
   */
  dedupeTick?: boolean;
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

/**
 * Dated backfill args (DIG-1335). The caller names the date; the tick supplies
 * it when the caller did not. Unlike houseArgs there is no force distinction:
 * a caller-supplied run_date is the whole point of the kick — the CTO's Oct-6
 * measurement was a non-force kick whose run_date was dropped — so it always
 * wins, and only a missing date falls back to the scheduled day.
 */
export function backfillArgs(
  bodyArgs: Record<string, string>,
  now: number,
): Record<string, string> {
  return {
    ...bodyArgs,
    run_date: bodyArgs.run_date ?? new Date(now).toISOString().slice(0, 10),
  };
}

function startedRun(job: Job, result: DispatchResult): StartedRun {
  const run: StartedRun = {
    job_id: job.id,
    status: result.container_status ?? (result.dry_run ? "dry_run" : "dispatched"),
  };
  if (result.run_id) run.run_id = result.run_id;
  return run;
}

/** The one Durable Object instance every cron-tick claim goes through. */
const START_COUNTER_NAME = "cron-ticks";

/** The slice of StartCounter this Worker uses on the tick path. */
type TickCounter = {
  claimSlot(key: string, slot: string): Promise<boolean>;
  confirmSlot(key: string, slot: string): Promise<void>;
  releaseSlot(key: string, slot: string): Promise<void>;
};

/**
 * The job a cron tick slot belongs to.
 *
 * The job id is in the key, not the workflow file: three rows dispatch
 * market_context_ingest.yml and five share pipeline-digiquant.yml, and each of
 * those is its own start.
 */
function tickKey(cron: string, job: Job): string {
  return `${cron}\n${job.id}`;
}

/**
 * The cron minute a tick is owed in, as `YYYY-MM-DDTHH:MM`.
 *
 * The two deliveries of one tick do NOT share `scheduledTime`: the 00:52 slot
 * arrived as 00:52:48 and 00:52:55, so a claim on the exact time would claim
 * twice and dedupe nothing. A cron expression fires at most once per minute, so
 * one job owes at most one dispatch per (cron, minute) and no legitimate start
 * is ever collapsed. Two rows on one workflow file still differ here, because
 * the key carries the row.
 */
function tickSlot(scheduledTime: number): string {
  return new Date(scheduledTime).toISOString().slice(0, 16);
}

function tickCounter(env: Env): TickCounter | undefined {
  if (!env.START_COUNTER) return undefined;
  return env.START_COUNTER.get(
    env.START_COUNTER.idFromName(START_COUNTER_NAME),
  ) as unknown as TickCounter;
}

/** One warning per isolate is enough for a binding that is missing entirely. */
let warnedUnboundCounter = false;

/**
 * True when this delivery owns the slot, false when another delivery of the
 * same tick already claimed it.
 *
 * Fails OPEN on every failure: a missing binding or an unreachable counter
 * dispatches anyway. A duplicate run costs Actions minutes, a dropped tick
 * costs a production clock, so the claim is only ever allowed to remove a
 * duplicate, never a start.
 */
async function claimTick(
  env: Env,
  cron: string,
  job: Job,
  scheduledTime: number,
): Promise<boolean> {
  try {
    const counter = tickCounter(env);
    if (!counter) {
      if (!warnedUnboundCounter) {
        warnedUnboundCounter = true;
        console.error(JSON.stringify({ cron, job: job.id, error: "start_counter_unbound" }));
      }
      return true;
    }
    return await counter.claimSlot(tickKey(cron, job), tickSlot(scheduledTime));
  } catch (err) {
    console.error(
      JSON.stringify({
        cron,
        job: job.id,
        error: "start_counter_unreachable",
        detail: err instanceof Error ? err.message : String(err),
      }),
    );
    return true;
  }
}

/**
 * Mark the claim as accepted once the dispatch resolved, so the lease can no
 * longer hand the slot to a later delivery. A failure here is logged and
 * swallowed: the run already started, and a claim that expires is a duplicate
 * risk, not a lost clock.
 */
async function confirmTick(
  env: Env,
  cron: string,
  job: Job,
  scheduledTime: number,
): Promise<void> {
  try {
    const counter = tickCounter(env);
    if (!counter) return;
    await counter.confirmSlot(tickKey(cron, job), tickSlot(scheduledTime));
  } catch (err) {
    console.error(
      JSON.stringify({
        cron,
        job: job.id,
        error: "start_counter_confirm_failed",
        detail: err instanceof Error ? err.message : String(err),
      }),
    );
  }
}

/**
 * Give the slot back after a failed dispatch, so the next delivery of the same
 * tick can start the run. Nothing started upstream, so re-claiming cannot
 * duplicate a run.
 */
async function releaseTick(
  env: Env,
  cron: string,
  job: Job,
  scheduledTime: number,
): Promise<void> {
  try {
    const counter = tickCounter(env);
    if (!counter) return;
    await counter.releaseSlot(tickKey(cron, job), tickSlot(scheduledTime));
  } catch (err) {
    console.error(
      JSON.stringify({
        cron,
        job: job.id,
        error: "start_counter_release_failed",
        detail: err instanceof Error ? err.message : String(err),
      }),
    );
  }
}

/**
 * The claim, or an already-owned slot when this caller does not dedupe. /kick
 * passes dedupeTick off: a human typing a cron by hand is not a duplicate
 * delivery, and the same cron may be kicked twice on purpose.
 */
function claimTickIfAsked(
  env: Env,
  cron: string,
  job: Job,
  scheduledTime: number,
  opts: RunOptions,
): Promise<boolean> {
  return opts.dedupeTick ? claimTick(env, cron, job, scheduledTime) : Promise.resolve(true);
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
  const pending: Promise<StartedRun | undefined>[] = [];

  if (jobs.length === 0) {
    const violation = unrecognisedCronViolation(cron);
    // Still one line per occurrence for observability search, now carrying the
    // class. Before DIG-732 this was the whole response to a trigger that fires
    // with nothing behind it.
    console.error(
      JSON.stringify({ cron, error: "unmapped_cron", alarm_class: violation.class }),
    );
    // A cron whose only owner is a deliberately disabled job (`house-run-10/11/12`
    // keep their cron lines as retry slots) is a known configuration, not drift.
    // Alarming on it would cry wolf three times a day. Alarm only when no job
    // row at all claims the cron.
    const knownDisabledSlot = jobsForCron(cron, { includeDisabled: true }).length > 0;
    if (opts.alarmUnmapped && !knownDisabledSlot) {
      // waitUntil, not await: the tick has nothing to dispatch, and the alarm
      // must not become a reason for scheduled() to throw.
      ctx.waitUntil(
        raiseViolationAlarms(env, [violation], "the deployed trigger list, at the tick that fired"),
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
    } else if (job.id === "twelve-x-backfill") {
      args = backfillArgs(opts.args ?? {}, scheduledTime);
    }
    pending.push(
      claimTickIfAsked(env, cron, job, scheduledTime, opts).then((owned) => {
        if (!owned) {
          // The tick already dispatched this job. Log instead of dispatching:
          // one line per skipped duplicate keeps the double delivery visible
          // without starting the workflow again.
          console.log(
            JSON.stringify({
              cron,
              repo: job.repo,
              job: job.id,
              skipped: "duplicate_tick",
              scheduled_time: scheduledTime,
            }),
          );
          return undefined;
        }
        return dispatch(env, job, cron, scheduledTime, { args, force: opts.force === true })
          .then(async (result) => {
            // The dispatch was accepted, so this slot stays claimed for good.
            // A confirm failure only shortens the claim to its lease.
            if (opts.dedupeTick) await confirmTick(env, cron, job, scheduledTime);
            return startedRun(job, result);
          })
          .catch(async (err: unknown) => {
            const msg = err instanceof Error ? err.message : String(err);
            console.error(JSON.stringify({ cron, job: job.id, error: msg }));
            // Nothing started upstream, so the slot goes back for the next
            // delivery of the same tick to try again.
            if (opts.dedupeTick) await releaseTick(env, cron, job, scheduledTime);
            throw err;
          });
      }),
    );
  }
  if (pending.length === 0) {
    return { started, skipped, runs: [] };
  }
  if (opts.awaitDispatch) {
    const results = await Promise.all(pending);
    return {
      started,
      skipped,
      runs: results.filter((run): run is StartedRun => run !== undefined),
    };
  }
  ctx.waitUntil(Promise.all(pending));
  return { started, skipped, runs: [] };
}

/**
 * Start keys already dispatched by this isolate. A repeat kick carrying the
 * same key is a duplicate and must not reach the runner a second time (A.4).
 * Best-effort and per-isolate by construction: it catches double-submits, not
 * cross-isolate races. Bounded so a long-lived isolate cannot grow it without
 * limit; eviction only risks a re-dispatch, never a dropped one.
 */
const seenStartKeys = new Set<string>();

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
      const release_failed = !(await writeLedger("release", () =>
        stub.release(split.toDispatch, split.claimedAt),
      ));
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
      // GitHub declined to start a run benignly — the body said a run for this
      // ref is already queued or already running, which `isBenign422` in
      // dispatch.ts is the only way to reach here. A disabled maintenance
      // workflow is NOT one of those cases: its 422 body matches no benign
      // substring, so `postGithub` throws and the catch below answers 502
      // instead. No run exists for these dates either way, so this is NOT
      // remediation: recording `done` is what let a later retry answer
      // "already remediated" for a date that was never backfilled, forever. The
      // dates settle as `dispatch_suppressed`, stay claimable for the next POST,
      // and the caller gets 409 — not the 200 that claimed success.
      const ledger_write_failed = !(
        await writeLedger("markSuppressed", () =>
          stub.markSuppressed(split.toDispatch, now, result.status, split.claimedAt),
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
      await writeLedger("markDone", () =>
        stub.markDone(split.toDispatch, now, split.claimedAt),
      )
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
    const release_failed = !(await writeLedger("release", () =>
        stub.release(split.toDispatch, split.claimedAt),
      ));
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
    await runJobsForCron(controller.cron, controller.scheduledTime, env, ctx, {
      alarmUnmapped: true,
      dedupeTick: true,
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
      let requestedTime: number | undefined;
      let startKey: string | undefined;
      try {
        const body = (await request.json()) as {
          cron?: unknown;
          force?: unknown;
          args?: unknown;
          scheduledTime?: unknown;
          startKey?: unknown;
        };
        cron = typeof body.cron === "string" ? body.cron : "";
        force = body.force === true;
        const parsedArgs = parseStringArgs(body.args);
        if (parsedArgs === null) {
          return Response.json({ error: "invalid_args" }, { status: 400 });
        }
        args = parsedArgs;
        if (body.scheduledTime !== undefined) {
          // A non-numeric or fractional value is a caller mistake, not a
          // coercion hint: reject it here so it can never reach the start key
          // as NaN. Number.isInteger is false for NaN and both infinities.
          if (typeof body.scheduledTime !== "number" || !Number.isInteger(body.scheduledTime)) {
            return Response.json({ error: "invalid_args" }, { status: 400 });
          }
          requestedTime = body.scheduledTime;
        }
        if (body.startKey !== undefined) {
          if (typeof body.startKey !== "string" || body.startKey.length === 0) {
            return Response.json({ error: "invalid_args" }, { status: 400 });
          }
          startKey = body.startKey;
        }
      } catch {
        return Response.json({ error: "invalid_json" }, { status: 400 });
      }
      if (!cron) {
        return Response.json({ error: "cron_required" }, { status: 400 });
      }
      // One derivation, at the kick boundary. Flooring to the wall-clock minute
      // gives a repeat kick inside the same minute the same scheduledTime. A
      // kick is a distinct namespace from the cron path and does not resolve
      // to the cron's firing slot: see DIG-47 spec section 9, decision D3.
      const scheduledTime = requestedTime ?? Math.floor(Date.now() / 60_000) * 60_000;
      // The start key names one kick. Only an explicit key dedupes: a
      // repeat kick carrying the same key is a double-submit and answers 200
      // without reaching the runner again (A.4). Kicks without a key always
      // dispatch — deriving a key from the cron and minute here would
      // wrongly collapse distinct kicks that happen to share a minute.
      if (startKey !== undefined) {
        const key = `${cron}\n${startKey}`;
        if (seenStartKeys.has(key)) {
          return Response.json(
            { ok: true, cron, started: [], skipped: [], runs: [], duplicate: true },
            { status: 200 },
          );
        }
        if (seenStartKeys.size >= 5000) seenStartKeys.clear();
        seenStartKeys.add(key);
      }
      let result;
      try {
        result = await runJobsForCron(cron, scheduledTime, env, ctx, {
          force,
          args,
          awaitDispatch: true,
          includeDisabled: true,
        });
      } catch (error) {
        // The caller's own input is what GitHub refused, so it is a 400 and
        // the message names the key. Every other failure keeps its old shape
        // and still throws out of the route.
        const detail = error instanceof Error ? error.message : String(error);
        if (detail.startsWith(UNDECLARED_INPUT)) {
          return Response.json({ error: UNDECLARED_INPUT, cron, detail }, { status: 400 });
        }
        throw error;
      }
      return Response.json({ ok: true, cron, ...result }, { status: 200 });
    }

    if (request.method === "POST" && path === "/backfill") {
      return handleBackfill(request, env);
    }

    return new Response("Not Found", { status: 404 });
  },
};

export type { Env, Job };
