/**
 * Detect a digiquant house run that never landed (DIG-3065).
 *
 * `GET /healthz` on digiquant-runner answers with `running: string[]` — exactly
 * the run ids still holding a lock (see `health()` in
 * `apps/digiquant-runner/src/runner-session.ts`). A run that loses its container
 * or its Durable Object keeps its lock: it stays in `running` with no
 * `finished_at` and no exit code, and nothing else in the cadence notices. The
 * Monday 09:17 start already returned 202, and the retry slots
 * (`house-run-10/11/12`) are deliberately disabled — so a lost run is silent
 * until a human reads the board. This watcher is the clock instead.
 *
 * It reads the same two routes an operator would read by hand:
 *
 *   GET /healthz              -> which run ids the runner still calls running
 *   GET /v1/jobs/<run_id>     -> that run's live record (needs the bearer token)
 *
 * and raises when a run the runner still calls running is open past the deadline
 * the house-run job row declares, plus the runner's own watchdog grace.
 *
 * Two rules this file holds to:
 *
 * - **Read-only.** It never POSTs to `/v1/jobs`, never re-kicks, never re-runs
 *   and never redeploys. A watcher that repairs is a second thing with its own
 *   blast radius, and only Chris authorises that.
 * - **Fail quiet.** A transport fault, a 401, or unparseable JSON makes a run
 *   *unreadable*, never *lost*. Only a run this code actually read — HTTP 200,
 *   parsed — can be raised. An alarm that fires on its own failure mode is worse
 *   than no alarm, because it teaches the reader to ignore it. This is the same
 *   rule `probe.ts` states as `INCONCLUSIVE_STATUSES`.
 *
 * `error: "house_run_lost"` on the run record is the runner reporting the same
 * thing directly (PR #5488). It is read when present and never required, so this
 * watcher is correct before and after that lands.
 *
 * DIG-4416 added the dispatch-confirmation arm. On 2026-10-19 the Monday 09:17
 * tick fired, the runner saw no POST, and nothing said so for four hours: the
 * only Monday check waited for the run deadline, and a run that never started
 * has no lock for the lost-run arm to read. That arm now asks a sharper
 * question five minutes after the start — did the runner accept a house run for
 * today at all — using the `dispatched` field on `GET /v1/jobs/house-status`.
 * The four-hour arm keeps the other, disjoint class: accepted but never landed.
 *
 * The alarm follows the house convention in `trigger-alarm.ts` — the label is
 * the class, the issue is the occurrence, one issue per occurrence, never a
 * comment on an open issue, and raising never throws. Its helpers are hard-typed
 * to `TriggerAlarm` and covered by a 320-line sibling suite, so they are
 * deliberately not shared here; that duplication is a known, stated deviation.
 */

/** Mirrors `WATCHDOG_GRACE_SECONDS` in `apps/digiquant-runner/src/runner-session.ts`. */
export const WATCHDOG_GRACE_SECONDS = 120;

/**
 * How long the runner gets to accept the Monday POST before the dispatch is
 * called missing (DIG-4416). The hand-off is a single service-binding POST; at
 * 09:22, five minutes after the 09:17 start, there is no honest reading left.
 */
export const DISPATCH_CONFIRM_GRACE_SECONDS = 300;

/** The only job target this watcher knows how to read. */
export const WATCH_TARGET = "digiquant-runner";

/** The error the runner stamps on a run it has written off (PR #5488). */
export const HOUSE_RUN_LOST_ERROR = "house_run_lost";

/**
 * The alarm class. One label for the class, one issue per occurrence — the
 * `trigger-alarm.ts` convention. Digithings, not twelve-x: house-run is the
 * digiquant pipeline, and `GH_DISPATCH_TOKEN` carries Issues write on both repos.
 */
export const HOUSE_RUN_WATCH_LABEL = "digiquant-house-run-not-landed";
export const ALERT_REPO = "digithings-ai/digithings";

/**
 * The board-side run-watch key recorded on DIG-3061. The Worker cannot reach the
 * Paperclip board — `GH_DISPATCH_TOKEN` is a GitHub credential and there is no
 * board token in the cron Env — so this watcher cannot comment there itself.
 * The key travels in the issue body instead, so the recurrence is filed once,
 * in one place, and a repeat of the same condition is recognisable.
 */
export const RUN_WATCH_KEY = "run-watch:digiquant-house-run:no-book";

export const RUNNER_HEALTH_URL = `https://${WATCH_TARGET}/healthz`;

export function runnerRunUrl(runId: string): string {
  return `https://${WATCH_TARGET}/v1/jobs/${encodeURIComponent(runId)}`;
}

/** Dependency-injected fetch, the same seam `probe.ts` uses to drive its tests. */
export type WatchFetch = (input: string, init?: RequestInit) => Promise<Response>;

/** Only a 200 is evidence on a read. Everything else is unreadable, never lost. */
export const OK_STATUSES = new Set([200]);

/**
 * GitHub answers 201 Created when it makes an issue. Reusing the read set here
 * would silently discard every successful alarm — a write that succeeded and was
 * reported as unraised, which is the worst possible direction for a detector.
 */
const WRITE_OK_STATUSES = new Set([200, 201]);

const TERMINAL_STATUSES = new Set(["succeeded", "failed", "timed_out"]);

/** The subset of the run record `publicRun()` returns that this watcher reads. */
export type HouseRunObservation = {
  run_id?: string;
  status?: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
};

export type HouseRunReason =
  | "runner-reported-lost"
  | "past-deadline"
  | "within-deadline"
  | "terminal"
  | "no-start";

export type HouseRunVerdict = {
  run_id: string;
  lost: boolean;
  reason: HouseRunReason;
  status: string;
  started_at: string | null;
  deadline_at: string | null;
  age_seconds: number | null;
};

export type RaisedAlarm = { run_id: string; raised: boolean; url?: string };

export type HouseRunCheckResult = {
  ok: boolean;
  checked_at: string;
  deadline_seconds: number;
  open: number;
  lost: HouseRunVerdict[];
  unreadable: string[];
  raised: RaisedAlarm[];
  /** Mondays the runner accepted but no landing followed (DIG-3456). */
  neverLanded: NeverLandedFinding[];
  /** Mondays whose 09:17 POST never reached the runner (DIG-4416). */
  missingDispatch: DispatchMissingFinding[];
};

/** Why a Monday with no landing is or is not the never-landed class. */
export type NeverLandedReason =
  | "not-due"
  | "unverifiable"
  | "landed"
  | "open-house-run"
  /** The confirm arm owns this Monday: no POST reached the runner at all. */
  | "not-dispatched"
  | "never-landed";

export type NeverLandedFinding = {
  run_date: string;
  lost: boolean;
  reason: NeverLandedReason;
};

/** Why a Monday with no accepted house run is or is not a missing dispatch. */
export type DispatchMissingReason =
  | "not-due"
  | "unverifiable"
  | "dispatched"
  | "missing-dispatch";

export type DispatchMissingFinding = {
  run_date: string;
  lost: boolean;
  reason: DispatchMissingReason;
};

/** The runner's landing answer for one run_date, or null when unreadable. */
export type HouseStatus = {
  run_date: string;
  landed: boolean;
  /** House runs holding a lock right now: `open_house_runs` in health. */
  open_house_runs: string[];
  /**
   * A house run for this run_date reached the runner, whatever state it is in.
   * `open_house_runs` cannot answer this: a run accepted while another job
   * holds a lock is queued and holds none (DIG-4416).
   *
   * `null` means the runner did not report the field. Both apps deploy from
   * `main` on separate workflows, so a cron newer than its runner is a real
   * window: unknown is not "not dispatched", and it is not a reason to lose the
   * older never-landed arm either.
   */
  dispatched: boolean | null;
  verifiable: boolean;
};

export function ghHeaders(token: string | undefined, json: boolean): Record<string, string> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token ?? ""}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "digithings-cron",
  };
  if (json) headers["Content-Type"] = "application/json";
  return headers;
}

/**
 * The deadline: the timeout the house-run job row declares, plus the runner's
 * own watchdog grace. `deadlineSeconds` is the job row's `timeout_seconds`
 * (14400) — the runner allows that long *plus* `WATCHDOG_GRACE_SECONDS` before
 * it stamps `timed_out`, so raising at `timeout_seconds` alone would race it.
 */
export function houseRunDeadlineSeconds(timeoutSeconds: number): number {
  return timeoutSeconds + WATCHDOG_GRACE_SECONDS;
}

/**
 * Decide one read run. Pure: `nowMs` and `deadlineSeconds` are both injected so
 * a test pins "open past the deadline" with no network and no clock.
 *
 * `lost` is true on exactly two conditions, both of which name a run the runner
 * itself is still holding open:
 *   - `error === "house_run_lost"` — the runner has already written it off
 *     (PR #5488). Read when present, never required.
 *   - open, with a start time, past `deadlineSeconds`.
 */
export function evaluateHouseRun(
  runId: string,
  observation: HouseRunObservation,
  opts: { nowMs: number; deadlineSeconds: number },
): HouseRunVerdict {
  const status = observation.status ?? "unknown";
  const startedAt = observation.started_at ?? null;
  const startedMs = startedAt ? Date.parse(startedAt) : Number.NaN;
  const hasStart = Number.isFinite(startedMs);
  const ageSeconds = hasStart ? Math.floor((opts.nowMs - startedMs) / 1000) : null;
  const deadlineAt = hasStart
    ? new Date(startedMs + opts.deadlineSeconds * 1000).toISOString()
    : null;

  const base = {
    run_id: runId,
    status,
    started_at: startedAt,
    deadline_at: deadlineAt,
    age_seconds: ageSeconds,
  };

  if (observation.error === HOUSE_RUN_LOST_ERROR) {
    return { ...base, lost: true, reason: "runner-reported-lost" };
  }
  if (TERMINAL_STATUSES.has(status)) {
    return { ...base, lost: false, reason: "terminal" };
  }
  if (!hasStart) {
    // Holding a lock with no start time. We cannot compute a deadline, so we
    // report it and do not raise: an unmeasurable run is not a measured one.
    return { ...base, lost: false, reason: "no-start" };
  }
  if (ageSeconds !== null && ageSeconds > opts.deadlineSeconds) {
    return { ...base, lost: true, reason: "past-deadline" };
  }
  return { ...base, lost: false, reason: "within-deadline" };
}

export function alarmTitle(verdict: HouseRunVerdict): string {
  return `digiquant house-run ${verdict.run_id} did not land`;
}

export function alarmBody(verdict: HouseRunVerdict, deadlineSeconds: number): string {
  const lines = [
    `The digiquant runner is still reporting \`${verdict.run_id}\` as open, past the deadline the house-run job declares.`,
    "",
    `- run id: \`${verdict.run_id}\``,
    `- status: \`${verdict.status}\``,
    `- reason: \`${verdict.reason}\``,
    `- started at: ${verdict.started_at ?? "unknown"}`,
    `- deadline: ${verdict.deadline_at ?? "unknown"} (timeout_seconds + ${WATCHDOG_GRACE_SECONDS}s watchdog grace = ${deadlineSeconds}s)`,
    `- age: ${verdict.age_seconds === null ? "unknown" : `${verdict.age_seconds}s`}`,
    `- read it: \`curl -H "Authorization: Bearer $RUNNER_AUTH_TOKEN" ${runnerRunUrl(verdict.run_id)}\``,
    "",
    `Run-watch key: \`${RUN_WATCH_KEY}\` (DIG-3061). A recurrence of the same condition belongs on that key, not in a new ticket.`,
    "",
    "**This watcher is read-only.** It has not re-kicked, re-run, redeployed or rolled anything back, and will not. Repair is Chris's call.",
    "",
    `Detector: DIG-3065, hourly (\`22 * * * *\`). Root-cause repair: DIG-3061 item 2 (PR #5488).`,
  ];
  return lines.join("\n");
}

async function readJson(
  fetcher: WatchFetch,
  url: string,
  headers: Record<string, string>,
): Promise<{ status: number; body: unknown }> {
  const response = await fetcher(url, { method: "GET", headers });
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  return { status: response.status, body };
}

/** GET /healthz. No Authorization: the runner serves healthz before its auth gate. */
export async function readOpenRuns(fetcher: WatchFetch): Promise<{
  ok: boolean;
  running: string[];
}> {
  const { status, body } = await readJson(fetcher, RUNNER_HEALTH_URL, ghHeaders(undefined, false));
  if (!OK_STATUSES.has(status) || body === null || typeof body !== "object") {
    return { ok: false, running: [] };
  }
  const running = (body as { running?: unknown }).running;
  if (!Array.isArray(running)) return { ok: false, running: [] };
  return { ok: true, running: running.filter((id): id is string => typeof id === "string") };
}

/** GET /v1/jobs/<run_id>. The runner's auth gate covers every /v1/jobs route. */
export async function readRun(
  fetcher: WatchFetch,
  runId: string,
  token: string | undefined,
): Promise<HouseRunObservation | null> {
  const { status, body } = await readJson(fetcher, runnerRunUrl(runId), ghHeaders(token, false));
  if (!OK_STATUSES.has(status) || body === null || typeof body !== "object") return null;
  return body as HouseRunObservation;
}

export function houseStatusUrl(runDate: string): string {
  return `https://digiquant-runner/v1/jobs/house-status?run_date=${encodeURIComponent(runDate)}`;
}

/**
 * GET /v1/jobs/house-status?run_date=. Strict shape check on purpose: a body
 * this code does not understand (a health body, a proxy page, anything) is
 * unreadable, never "not landed". Without this, every misrouted response
 * would read as a missing Monday run.
 */
export async function readHouseStatus(
  fetcher: WatchFetch,
  runDate: string,
  token: string | undefined,
): Promise<HouseStatus | null> {
  const { status, body } = await readJson(fetcher, houseStatusUrl(runDate), ghHeaders(token, false));
  if (!OK_STATUSES.has(status) || body === null || typeof body !== "object") return null;
  const row = body as Record<string, unknown>;
  if (row.run_date !== runDate) return null;
  if (typeof row.landed !== "boolean" || typeof row.verifiable !== "boolean") return null;
  // Absent or unrecognised is unknown, never false: the confirm arm must not
  // read a runner that predates the field as "no POST arrived" (DIG-4416).
  const dispatched = typeof row.dispatched === "boolean" ? row.dispatched : null;
  if (!Array.isArray(row.open_house_runs)) return null;
  if (!row.open_house_runs.every((id): id is string => typeof id === "string")) return null;
  return {
    run_date: runDate,
    landed: row.landed,
    open_house_runs: row.open_house_runs,
    dispatched,
    verifiable: row.verifiable,
  };
}

/**
 * The run_date the Monday 09:17 tick carries: the most recent Monday (UTC).
 * `houseArgs` stamps `run_date` as the scheduled day, so the expected
 * success.json key for any tick this week is under last Monday's date.
 */
export function lastMondayRunDate(nowMs: number): string {
  const now = new Date(nowMs);
  const daysSinceMonday = (now.getUTCDay() + 6) % 7;
  const monday = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - daysSinceMonday),
  );
  return monday.toISOString().slice(0, 10);
}

/** The Monday 09:17 UTC start house-run-09 declares, for a run_date Monday. */
export function mondayStartMs(runDate: string): number {
  return Date.parse(`${runDate}T09:17:00.000Z`);
}

/**
 * Decide one Monday at the dispatch-confirmation deadline (DIG-4416). Pure:
 * every input injected.
 *
 * `lost` is true on exactly one condition: past the confirm grace, the landing
 * read succeeded, no marker exists, and the runner holds no record of a house
 * run for that run_date. That is the operational fact the alarm reports: no
 * house run for today exists five minutes after the tick. Two causes produce
 * it, and the issue names both: the POST never reached the runner, or it
 * reached it while a job held the `digiquant-pipeline` lock and `accept()`
 * answered `already_running` without writing a record.
 *
 * `dispatched` is what makes this arm honest. A run accepted while another job
 * holds a lock is queued by `mustQueue()` and holds no lock, so
 * `open_house_runs` reads empty even though the POST landed. The 2026-10-19
 * Monday ran with a stale lock open, which is exactly that shape.
 * `open_house_runs` is deliberately NOT part of this test: it is not
 * date-scoped, so a hung run from an earlier Monday would silence the arm on
 * the one Monday it is for.
 */
export function evaluateDispatchMissing(
  runDate: string,
  opts: { nowMs: number; graceSeconds: number },
  status: HouseStatus | null,
): DispatchMissingFinding {
  const startMs = mondayStartMs(runDate);
  if (opts.nowMs < startMs + opts.graceSeconds * 1000) {
    return { run_date: runDate, lost: false, reason: "not-due" };
  }
  if (!status || !status.verifiable) {
    return { run_date: runDate, lost: false, reason: "unverifiable" };
  }
  if (status.dispatched === null) {
    return { run_date: runDate, lost: false, reason: "unverifiable" };
  }
  if (status.landed || status.dispatched) {
    return { run_date: runDate, lost: false, reason: "dispatched" };
  }
  return { run_date: runDate, lost: true, reason: "missing-dispatch" };
}

export function dispatchMissingTitle(runDate: string): string {
  return `digiquant house-run for ${runDate} never started on the runner`;
}

export function dispatchMissingBody(runDate: string, graceSeconds: number): string {
  const lines = [
    `The Monday ${runDate} house run is due, and the runner holds no house run for that date: not queued, not running, no success marker.`,
    "",
    `- run date: \`${runDate}\``,
    `- expected POST: Monday 09:17 UTC to \`https://digiquant-runner/v1/jobs\``,
    `- confirm deadline: Monday 09:17 UTC + ${graceSeconds}s`,
    `- expected marker: \`pipeline-runs/house-run/${runDate}/success.json\``,
    `- read it: \`GET https://digiquant-runner/v1/jobs/house-status?run_date=${runDate}\` (runner bearer token)`,
    "",
    `This is the missing-dispatch class: no house run for ${runDate} reached the runner's ledger. Two causes give this shape, and the ledger cannot tell them apart after the fact:`,
    "",
    `1. **The POST never reached the runner.** The clock fired and the request was lost between \`digithings-cron\` and \`digiquant-runner\`.`,
    `2. **The POST arrived while the \`digiquant-pipeline\` lock was held.** \`accept()\` answers \`already_running\` and writes no run record, so nothing queued and nothing started.`,
    "",
    `Both leave the same hole — no house run for ${runDate} — and both take the same repair: a forced house run. This is not the never-landed class (that run is in the ledger) and not the lost-run class (nothing is open).`,
    "",
    `Run-watch key: \`${RUN_WATCH_KEY}\` (DIG-3061). A recurrence of the same condition belongs on that key, not in a new ticket.`,
    "",
    "**This watcher is read-only.** It has not re-kicked, re-run, redeployed or rolled anything back, and will not. Repair is Chris's call.",
    "",
    `Detector: DIG-4416, hourly (\`22 * * * *\`), five minutes after the Monday tick.`,
  ];
  return lines.join("\n");
}

/** Raising never throws, exactly as `trigger-alarm.ts` states. */
export async function raiseDispatchMissingAlarm(
  token: string | undefined,
  runDate: string,
  graceSeconds: number,
  fetcher: WatchFetch,
): Promise<RaisedAlarm> {
  const run_id = `house-run:${runDate}`;
  const title = dispatchMissingTitle(runDate);
  try {
    const existing = await findOpenOccurrence(fetcher, token, title);
    if (existing) return { run_id, raised: false, url: existing };
    await ensureLabel(fetcher, token);
    const { status, body } = await postJson(
      fetcher,
      `https://api.github.com/repos/${ALERT_REPO}/issues`,
      token,
      { title, body: dispatchMissingBody(runDate, graceSeconds), labels: [HOUSE_RUN_WATCH_LABEL] },
    );
    if (!WRITE_OK_STATUSES.has(status)) return { run_id, raised: false };
    const html = (body as { html_url?: unknown } | null)?.html_url;
    return typeof html === "string" ? { run_id, raised: true, url: html } : { run_id, raised: false };
  } catch {
    return { run_id, raised: false };
  }
}

/**
 * Decide one Monday at the run deadline (DIG-3456, refocused by DIG-4416).
 * Pure: every input injected, so "a dispatched run that left no marker" is an
 * arithmetic fact rather than a timing race.
 *
 * `lost` is true on exactly one condition: past the deadline for last Monday's
 * start, the landing read succeeded and says absent, the runner accepted a
 * house run for that date, and no house run is still open. A Monday with no
 * accepted run is `not-dispatched` and quiet here: the confirm arm owns it and
 * fires five minutes after the tick, not four hours after.
 */
export function evaluateNeverLanded(
  runDate: string,
  opts: { nowMs: number; deadlineSeconds: number },
  status: HouseStatus | null,
): NeverLandedFinding {
  const startMs = mondayStartMs(runDate);
  if (!(opts.nowMs > startMs + opts.deadlineSeconds * 1000)) {
    return { run_date: runDate, lost: false, reason: "not-due" };
  }
  if (!status || !status.verifiable) {
    return { run_date: runDate, lost: false, reason: "unverifiable" };
  }
  if (status.landed) {
    return { run_date: runDate, lost: false, reason: "landed" };
  }
  if (status.open_house_runs.length > 0) {
    return { run_date: runDate, lost: false, reason: "open-house-run" };
  }
  if (status.dispatched === false) {
    return { run_date: runDate, lost: false, reason: "not-dispatched" };
  }
  return { run_date: runDate, lost: true, reason: "never-landed" };
}

export function neverLandedTitle(runDate: string): string {
  return `digiquant house-run for ${runDate} never landed`;
}

export function neverLandedBody(
  runDate: string,
  deadlineSeconds: number,
  dispatchKnown = true,
): string {
  const lines = [
    dispatchKnown
      ? `The runner accepted a house run for Monday ${runDate}, no house run is open, and no success marker exists past the deadline.`
      : `No success marker exists for Monday ${runDate} past the deadline, no house run is open, and the runner did not report whether it accepted one (it predates the \`dispatched\` field).`,
    "",
    `- run date: \`${runDate}\``,
    `- expected marker: \`pipeline-runs/house-run/${runDate}/success.json\``,
    `- deadline: Monday 09:17 UTC + ${deadlineSeconds}s (timeout_seconds + ${WATCHDOG_GRACE_SECONDS}s watchdog grace)`,
    `- read it: \`GET https://digiquant-runner/v1/jobs/house-status?run_date=${runDate}\` (runner bearer token)`,
    "",
    dispatchKnown
      ? `This is the never-landed class: the POST arrived, the run left no lock and no marker. A Monday with no accepted run at all is the missing-dispatch class and is filed five minutes after the tick.`
      : `The runner could not say whether it accepted a run, so this covers both classes: a missing POST, or an accepted run that left no lock and no marker. The cron's confirm arm reports the first from five minutes after the tick once the runner reports \`dispatched\`.`,
    "",
    `Run-watch keys: \`${RUN_WATCH_KEY}\` (DIG-3061) and \`run-watch:house-run:no-dispatch-since-2026-09-28\` (DIG-3456). A recurrence of the same condition belongs on those keys, not in a new ticket.`,
    "",
    "**This watcher is read-only.** It has not re-kicked, re-run, redeployed or rolled anything back, and will not. Repair is Chris's call.",
    "",
    `Detector: DIG-3456, hourly (\`22 * * * *\`) beside the DIG-4416 confirm arm.`,
  ];
  return lines.join("\n");
}

/** Raising never throws, exactly as `trigger-alarm.ts` states. */
export async function raiseNeverLandedAlarm(
  token: string | undefined,
  runDate: string,
  deadlineSeconds: number,
  fetcher: WatchFetch,
  dispatchKnown = true,
): Promise<RaisedAlarm> {
  const run_id = `house-run:${runDate}`;
  const title = neverLandedTitle(runDate);
  try {
    const existing = await findOpenOccurrence(fetcher, token, title);
    if (existing) return { run_id, raised: false, url: existing };
    await ensureLabel(fetcher, token);
    const { status, body } = await postJson(
      fetcher,
      `https://api.github.com/repos/${ALERT_REPO}/issues`,
      token,
      {
        title,
        body: neverLandedBody(runDate, deadlineSeconds, dispatchKnown),
        labels: [HOUSE_RUN_WATCH_LABEL],
      },
    );
    if (!WRITE_OK_STATUSES.has(status)) return { run_id, raised: false };
    const html = (body as { html_url?: unknown } | null)?.html_url;
    return typeof html === "string" ? { run_id, raised: true, url: html } : { run_id, raised: false };
  } catch {
    return { run_id, raised: false };
  }
}

async function ensureLabel(fetcher: WatchFetch, token: string | undefined): Promise<void> {
  const headers = ghHeaders(token, true);
  const existing = await fetcher(
    `https://api.github.com/repos/${ALERT_REPO}/labels/${HOUSE_RUN_WATCH_LABEL}`,
    { method: "GET", headers },
  );
  if (existing.status !== 404) return;
  await fetcher(`https://api.github.com/repos/${ALERT_REPO}/labels`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      name: HOUSE_RUN_WATCH_LABEL,
      color: "d73a4a",
      description: "A digiquant house run the runner still reports open, past its deadline",
    }),
  });
}

/**
 * The open occurrence of this exact drift, or null. Matches on the
 * deterministic title, and never returns a match it did not read: a non-200 or a
 * non-array body yields null so the caller raises rather than silently deduping
 * against something unverified.
 */
async function findOpenOccurrence(
  fetcher: WatchFetch,
  token: string | undefined,
  title: string,
): Promise<string | null> {
  const url =
    `https://api.github.com/repos/${ALERT_REPO}/issues?state=open` +
    `&labels=${encodeURIComponent(HOUSE_RUN_WATCH_LABEL)}&per_page=100`;
  const { status, body } = await readJson(fetcher, url, ghHeaders(token, false));
  if (!OK_STATUSES.has(status) || !Array.isArray(body)) return null;
  for (const row of body) {
    if (row && typeof row === "object" && (row as { title?: unknown }).title === title) {
      const html = (row as { html_url?: unknown }).html_url;
      return typeof html === "string" ? html : null;
    }
  }
  return null;
}

/** Raising never throws, exactly as `trigger-alarm.ts` states. */
export async function raiseHouseRunAlarm(
  token: string | undefined,
  verdict: HouseRunVerdict,
  deadlineSeconds: number,
  fetcher: WatchFetch,
): Promise<RaisedAlarm> {
  const title = alarmTitle(verdict);
  try {
    const existing = await findOpenOccurrence(fetcher, token, title);
    if (existing) return { run_id: verdict.run_id, raised: false, url: existing };
    await ensureLabel(fetcher, token);
    const { status, body } = await postJson(
      fetcher,
      `https://api.github.com/repos/${ALERT_REPO}/issues`,
      token,
      { title, body: alarmBody(verdict, deadlineSeconds), labels: [HOUSE_RUN_WATCH_LABEL] },
    );
    if (!WRITE_OK_STATUSES.has(status)) return { run_id: verdict.run_id, raised: false };
    const html = (body as { html_url?: unknown } | null)?.html_url;
    return typeof html === "string"
      ? { run_id: verdict.run_id, raised: true, url: html }
      : { run_id: verdict.run_id, raised: false };
  } catch {
    return { run_id: verdict.run_id, raised: false };
  }
}

async function postJson(
  fetcher: WatchFetch,
  url: string,
  token: string | undefined,
  payload: Record<string, unknown>,
): Promise<{ status: number; body: unknown }> {
  const response = await fetcher(url, {
    method: "POST",
    headers: ghHeaders(token, true),
    body: JSON.stringify(payload),
  });
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  return { status: response.status, body };
}

/**
 * One tick of the watcher. Read the runner, evaluate every open run against the
 * house-run deadline, raise one issue per lost run, then evaluate the two
 * Monday arms (dispatch confirmation at +5 min, never-landed at the run
 * deadline), and report what could not be read without raising on it.
 */
export async function checkHouseRuns(opts: {
  fetchRunner: WatchFetch;
  fetchGithub: WatchFetch;
  runnerToken?: string;
  githubToken?: string;
  timeoutSeconds: number;
  nowMs?: number;
  /** Overridable for tests; the Worker always uses the constant. */
  dispatchGraceSeconds?: number;
}): Promise<HouseRunCheckResult> {
  const nowMs = opts.nowMs ?? Date.now();
  const deadlineSeconds = houseRunDeadlineSeconds(opts.timeoutSeconds);
  const dispatchGraceSeconds = opts.dispatchGraceSeconds ?? DISPATCH_CONFIRM_GRACE_SECONDS;
  const result: HouseRunCheckResult = {
    ok: false,
    checked_at: new Date(nowMs).toISOString(),
    deadline_seconds: deadlineSeconds,
    open: 0,
    lost: [],
    unreadable: [],
    raised: [],
    neverLanded: [],
    missingDispatch: [],
  };

  if (!opts.runnerToken) {
    console.log(
      `${RUN_WATCH_KEY}: RUNNER_AUTH_TOKEN is unset; per-run status is unreadable this tick`,
    );
  }

  const health = await readOpenRuns(opts.fetchRunner);
  if (!health.ok) {
    console.log(`${RUN_WATCH_KEY}: runner /healthz unreadable; nothing evaluated`);
    return result;
  }
  result.ok = true;
  result.open = health.running.length;

  for (const runId of health.running) {
    const observation = await readRun(opts.fetchRunner, runId, opts.runnerToken);
    if (!observation) {
      result.unreadable.push(runId);
      continue;
    }
    const verdict = evaluateHouseRun(runId, observation, { nowMs, deadlineSeconds });
    if (!verdict.lost) continue;
    result.lost.push(verdict);
    result.raised.push(
      await raiseHouseRunAlarm(opts.githubToken, verdict, deadlineSeconds, opts.fetchGithub),
    );
  }

  // The Monday arms. The loop above only sees runs the runner still holds
  // open; a Monday whose POST never arrived leaves nothing open, so open=0
  // reads healthy here. Both arms read the same landing answer and are
  // disjoint by construction:
  //   - confirm (DIG-4416): no accepted run and no marker, five minutes after
  //     the start. The earliest point the missing POST is provable.
  //   - never-landed (DIG-3456): accepted, but no lock and no marker at the run
  //     deadline. `not-dispatched` is quiet here because the confirm arm owns it.
  // Both run on every tick; the not-due and landed arms are what keep them
  // quiet six days a week.
  const runDate = lastMondayRunDate(nowMs);
  const status = await readHouseStatus(opts.fetchRunner, runDate, opts.runnerToken);

  const missing = evaluateDispatchMissing(
    runDate,
    { nowMs, graceSeconds: dispatchGraceSeconds },
    status,
  );
  if (missing.lost) {
    result.missingDispatch.push(missing);
    result.raised.push(
      await raiseDispatchMissingAlarm(
        opts.githubToken,
        runDate,
        dispatchGraceSeconds,
        opts.fetchGithub,
      ),
    );
  }

  const never = evaluateNeverLanded(runDate, { nowMs, deadlineSeconds }, status);
  if (never.lost) {
    result.neverLanded.push(never);
    result.raised.push(
      await raiseNeverLandedAlarm(
        opts.githubToken,
        runDate,
        deadlineSeconds,
        opts.fetchGithub,
        status?.dispatched !== null,
      ),
    );
  }
  return result;
}