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
 * The alarm follows the house convention in `trigger-alarm.ts` — the label is
 * the class, the issue is the occurrence, one issue per occurrence, never a
 * comment on an open issue, and raising never throws. Its helpers are hard-typed
 * to `TriggerAlarm` and covered by a 320-line sibling suite, so they are
 * deliberately not shared here; that duplication is a known, stated deviation.
 */

/** Mirrors `WATCHDOG_GRACE_SECONDS` in `apps/digiquant-runner/src/runner-session.ts`. */
export const WATCHDOG_GRACE_SECONDS = 120;

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
  /** Mondays with no landing past the deadline and no open house run (DIG-3456). */
  neverDispatched: NeverDispatchedFinding[];
};

export type NeverDispatchedReason =
  | "not-due"
  | "unverifiable"
  | "landed"
  | "open-house-run"
  | "never-dispatched";

export type NeverDispatchedFinding = {
  run_date: string;
  lost: boolean;
  reason: NeverDispatchedReason;
};

/** The runner's landing answer for one run_date, or null when unreadable. */
export type HouseStatus = {
  run_date: string;
  landed: boolean;
  open_house_runs: string[];
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
    `Detector: DIG-3065, hourly (\`23 * * * *\`). Root-cause repair: DIG-3061 item 2 (PR #5488).`,
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
  if (!Array.isArray(row.open_house_runs)) return null;
  if (!row.open_house_runs.every((id): id is string => typeof id === "string")) return null;
  return {
    run_date: runDate,
    landed: row.landed,
    open_house_runs: row.open_house_runs,
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
 * Decide one Monday. Pure: every input injected, so "a Monday with no
 * landing" is an arithmetic fact rather than a timing race.
 *
 * `lost` is true on exactly one condition: past the deadline for last
 * Monday's start, the landing read succeeded and says absent, and no house
 * run is still open (an open one belongs to the past-deadline arm, which
 * reads the run itself rather than the absence of a marker).
 */
export function evaluateNeverDispatched(
  runDate: string,
  opts: { nowMs: number; deadlineSeconds: number },
  status: HouseStatus | null,
): NeverDispatchedFinding {
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
  return { run_date: runDate, lost: true, reason: "never-dispatched" };
}

export function neverDispatchedTitle(runDate: string): string {
  return `digiquant house-run for ${runDate} never landed`;
}

export function neverDispatchedBody(runDate: string, deadlineSeconds: number): string {
  const lines = [
    `No success marker exists for the Monday ${runDate} house run, past its deadline, and the runner holds no open house run for it.`,
    "",
    `- run date: \`${runDate}\``,
    `- expected marker: \`pipeline-runs/house-run/${runDate}/success.json\``,
    `- deadline: Monday 09:17 UTC + ${deadlineSeconds}s (timeout_seconds + ${WATCHDOG_GRACE_SECONDS}s watchdog grace)`,
    `- read it: \`GET https://digiquant-runner/v1/jobs/house-status?run_date=${runDate}\` (runner bearer token)`,
    "",
    `This is the never-dispatched class, not a lost run: the DIG-3065 arm watches runs the runner still reports open, and there is nothing open here. Either the Monday dispatch never reached the runner, or the run vanished without a lock. GHA silence is expected since the Oct-1 container cutover and is not evidence either way.`,
    "",
    `Run-watch keys: \`${RUN_WATCH_KEY}\` (DIG-3061) and \`run-watch:house-run:no-dispatch-since-2026-09-28\` (DIG-3456). A recurrence of the same condition belongs on those keys, not in a new ticket.`,
    "",
    "**This watcher is read-only.** It has not re-kicked, re-run, redeployed or rolled anything back, and will not. Repair is Chris's call.",
    "",
    `Detector: DIG-3456, hourly (\`23 * * * *\`) beside the DIG-3065 lost-run arm.`,
  ];
  return lines.join("\n");
}

/** Raising never throws, exactly as `trigger-alarm.ts` states. */
export async function raiseNeverDispatchedAlarm(
  token: string | undefined,
  runDate: string,
  deadlineSeconds: number,
  fetcher: WatchFetch,
): Promise<RaisedAlarm> {
  const run_id = `house-run:${runDate}`;
  const title = neverDispatchedTitle(runDate);
  try {
    const existing = await findOpenOccurrence(fetcher, token, title);
    if (existing) return { run_id, raised: false, url: existing };
    await ensureLabel(fetcher, token);
    const { status, body } = await postJson(
      fetcher,
      `https://api.github.com/repos/${ALERT_REPO}/issues`,
      token,
      { title, body: neverDispatchedBody(runDate, deadlineSeconds), labels: [HOUSE_RUN_WATCH_LABEL] },
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
 * house-run deadline, raise one issue per lost run, and report what could not be
 * read without raising on it.
 */
export async function checkHouseRuns(opts: {
  fetchRunner: WatchFetch;
  fetchGithub: WatchFetch;
  runnerToken?: string;
  githubToken?: string;
  timeoutSeconds: number;
  nowMs?: number;
}): Promise<HouseRunCheckResult> {
  const nowMs = opts.nowMs ?? Date.now();
  const deadlineSeconds = houseRunDeadlineSeconds(opts.timeoutSeconds);
  const result: HouseRunCheckResult = {
    ok: false,
    checked_at: new Date(nowMs).toISOString(),
    deadline_seconds: deadlineSeconds,
    open: 0,
    lost: [],
    unreadable: [],
    raised: [],
    neverDispatched: [],
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

  // The never-dispatched arm (DIG-3456). The loop above only sees runs the
  // runner still holds open; a Monday that never started leaves no lock, so
  // open=0 reads healthy here. The landing read below is what sees it. It
  // runs on every tick — the not-due and landed arms are what keep it quiet
  // six days a week — and it raises through the same one-issue-per-occurrence
  // dedup as the lost-run arm.
  const runDate = lastMondayRunDate(nowMs);
  const status = await readHouseStatus(opts.fetchRunner, runDate, opts.runnerToken);
  const never = evaluateNeverDispatched(runDate, { nowMs, deadlineSeconds }, status);
  if (never.lost) {
    result.neverDispatched.push(never);
    result.raised.push(
      await raiseNeverDispatchedAlarm(opts.githubToken, runDate, deadlineSeconds, opts.fetchGithub),
    );
  }
  return result;
}