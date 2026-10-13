/**
 * twelve-x checks that used to burn a GitHub Actions job each just to read the
 * Actions API (twelve-x is private, so every one of those runs was billed).
 * They now run inside this Worker on GH_DISPATCH_TOKEN:
 *
 *  - sessionCatchupDue: a gate in front of `session_catchup.yml`. The catch-up
 *    workflow still owns the real decision (pick_due_session.py + dated repair);
 *    this only skips the dispatch when the dedicated Asia/London/New York runs
 *    already cover every due slot today and every complete weekday in the
 *    3-day repair window. It is deliberately a superset: any doubt (read
 *    error, missing data) dispatches, so it can only remove no-op runs.
 *  - feed-confirm watchdog and desk session heartbeat watchdog: ports of
 *    feed_confirm_watchdog.yml and primarketet_heartbeat_watchdog.yml. Same
 *    labels, same thresholds, issues filed on digithings-ai/twelve-x.
 */
import { ghHeaders } from "./house-run-watch";
import { JOBS } from "./jobs";

/** The heartbeat workflow file, read from its own dispatch row (one home). */
export const HEARTBEAT_CRON = "3 6,18 * * *";
function heartbeatWorkflow(): string {
  const row = JOBS.find((j) => j.repo === REPO && j.cron === HEARTBEAT_CRON && j.kind === "workflow_dispatch");
  if (!row?.workflow) throw new Error("heartbeat dispatch row missing");
  return row.workflow;
}

export type GhFetch = (input: string, init?: RequestInit) => Promise<Response>;

const REPO = "digithings-ai/twelve-x";
const API = `https://api.github.com/repos/${REPO}`;
const PENDING = new Set(["in_progress", "queued", "waiting", "pending", "requested"]);

/** Same slots as twelve-x scripts/pick_due_session.py SESSION_SLOTS (UTC). */
export const SESSION_SLOTS: ReadonlyArray<[string, string, number]> = [
  ["asia", "daily_run_asia.yml", 0],
  ["london", "daily_run_london.yml", 7 * 60],
  ["new_york", "daily_run_new_york.yml", 12 * 60],
];
export const LOOKBACK_DAYS = 3;

type Run = {
  status?: string;
  conclusion?: string | null;
  created_at?: string;
  html_url?: string;
  id?: number;
  run_started_at?: string;
  updated_at?: string;
};

/**
 * What the catch-up itself already did, read from its job names (the same facts
 * session_catchup.yml reads): `fx-<session>` covers that session on the run's
 * date, `repair-<date>` latches that date so it is never offered again.
 */
export type CatchupFacts = {
  /** day -> sessions a success/in-flight catch-up run covered on that day */
  covered: Record<string, Set<string>>;
  /** dates already dispatched a dated repair */
  repaired: Set<string>;
};

/** A decide-only catch-up tick finishes in well under this; longer runs ran a job. */
const DECIDE_ONLY_MAX_MS = 45_000;

async function listRuns(
  fetcher: GhFetch,
  token: string | undefined,
  workflow: string,
  query: string,
): Promise<Run[]> {
  const res = await fetcher(`${API}/actions/workflows/${workflow}/runs?${query}`, {
    headers: ghHeaders(token, false),
  });
  if (res.status !== 200) throw new Error(`${workflow} runs HTTP ${res.status}`);
  const body = (await res.json()) as { workflow_runs?: Run[] };
  if (!Array.isArray(body.workflow_runs)) throw new Error(`${workflow} runs: bad body`);
  return body.workflow_runs;
}

const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);
const isWeekday = (ms: number) => {
  const d = new Date(ms).getUTCDay();
  return d >= 1 && d <= 5;
};

/** Days that must be fully covered for the gate to skip, oldest first. */
export function daysToCheck(nowMs: number): { today: string; past: string[] } {
  const past: string[] = [];
  for (let i = LOOKBACK_DAYS; i >= 1; i -= 1) {
    const ms = nowMs - i * 86_400_000;
    if (isWeekday(ms)) past.push(isoDay(ms));
  }
  return { today: isoDay(nowMs), past };
}

export type GateVerdict = { due: boolean; reason: string };

export function evaluateCatchup(
  nowMs: number,
  runsBySession: Record<string, Run[]>,
  facts: CatchupFacts = { covered: {}, repaired: new Set() },
): GateVerdict {
  const { today, past } = daysToCheck(nowMs);
  const now = new Date(nowMs);
  const minute = now.getUTCHours() * 60 + now.getUTCMinutes();
  for (const [name, , slot] of SESSION_SLOTS) {
    const runs = runsBySession[name] ?? [];
    const on = (day: string) => runs.filter((r) => (r.created_at ?? "").slice(0, 10) === day);
    const byCatchup = (day: string) => facts.covered[day]?.has(name) === true;
    if (isWeekday(nowMs) && minute >= slot) {
      const covered =
        byCatchup(today) ||
        on(today).some((r) => r.conclusion === "success" || PENDING.has(r.status ?? ""));
      if (!covered) return { due: true, reason: `${name} not covered ${today}` };
    }
    for (const day of past) {
      if (facts.repaired.has(day) || byCatchup(day)) continue;
      if (!on(day).some((r) => r.conclusion === "success")) {
        return { due: true, reason: `${name} not succeeded ${day}` };
      }
    }
  }
  return { due: false, reason: "all due sessions covered" };
}

/** Never throws. Any read failure answers due=true (fail open). */
export async function sessionCatchupDue(
  fetcher: GhFetch,
  token: string | undefined,
  nowMs: number,
): Promise<GateVerdict> {
  try {
    const since = isoDay(nowMs - (LOOKBACK_DAYS + 1) * 86_400_000);
    const runsBySession: Record<string, Run[]> = {};
    for (const [name, workflow] of SESSION_SLOTS) {
      runsBySession[name] = await listRuns(
        fetcher,
        token,
        workflow,
        `created=%3E%3D${since}&per_page=100`,
      );
    }
    const facts: CatchupFacts = { covered: {}, repaired: new Set() };
    const catchups = await listRuns(
      fetcher,
      token,
      "session_catchup.yml",
      `created=%3E%3D${since}&per_page=100`,
    );
    for (const run of catchups) {
      const pending = PENDING.has(run.status ?? "");
      const ok = run.conclusion === "success" || pending;
      const ms = Date.parse(run.updated_at ?? "") - Date.parse(run.run_started_at ?? run.created_at ?? "");
      if (!pending && !(ms > DECIDE_ONLY_MAX_MS)) continue;
      const res = await fetcher(`${API}/actions/runs/${run.id}/jobs?per_page=100`, {
        headers: ghHeaders(token, false),
      });
      if (res.status !== 200) throw new Error(`catch-up jobs HTTP ${res.status}`);
      const jobs = ((await res.json()) as { jobs?: Array<{ name?: string }> }).jobs ?? [];
      const day = (run.created_at ?? "").slice(0, 10);
      for (const { name = "" } of jobs) {
        const repair = /repair-(\d{4}-\d{2}-\d{2})/.exec(name);
        if (repair) facts.repaired.add(repair[1]);
        const fx = /fx-(asia|london|new_york)/.exec(name);
        if (fx && ok) (facts.covered[day] ??= new Set()).add(fx[1]);
      }
    }
    return evaluateCatchup(nowMs, runsBySession, facts);
  } catch (err) {
    return { due: true, reason: `gate_unreadable: ${err instanceof Error ? err.message : String(err)}` };
  }
}

// ---------------------------------------------------------------- watchdogs

export type TwelvexWatch = "feed-confirm" | "session-heartbeat";
export type WatchOutcome = { ok: boolean; alarm: boolean; filed?: string; detail: string };

export const FEED_LOOKBACK_HOURS = 6;
export const HEARTBEAT_TOLERANCE_HOURS = 18;

export function evaluateFeedConfirm(nowMs: number, runs: Run[] | null): { alarm: boolean; detail: string } {
  if (runs === null) return { alarm: true, detail: "run history unreadable" };
  const since = nowMs - FEED_LOOKBACK_HOURS * 3_600_000;
  const recent = runs.filter((r) => Date.parse(r.created_at ?? "") >= since);
  const completed = recent.filter((r) => r.status === "completed");
  if (completed.length > 0) return { alarm: false, detail: `${completed.length} completed` };
  return {
    alarm: true,
    detail:
      recent.length === 0
        ? "No confirm run was even started in the window."
        : recent.map((r) => `- \`${r.status}\` — ${r.html_url}`).join("\n"),
  };
}

export function evaluateHeartbeat(nowMs: number, runs: Run[] | null): { alarm: boolean; detail: string } {
  if (runs === null) return { alarm: true, detail: "run history unreadable" };
  const last = runs[0];
  if (!last) return { alarm: true, detail: "no heartbeat dispatch recorded" };
  const age = (nowMs - Date.parse(last.created_at ?? "")) / 3_600_000;
  const detail = `last dispatch ${last.id} at ${last.created_at} (${age.toFixed(1)}h ago, ${last.conclusion ?? last.status}) ${last.html_url}`;
  return { alarm: !(age <= HEARTBEAT_TOLERANCE_HOURS), detail };
}

const FEED_LABEL = "feed-confirm-silent";
const HB_LABEL = "primarketet-heartbeat-missing";

async function fileIssue(
  fetcher: GhFetch,
  token: string | undefined,
  label: string,
  color: string,
  title: string,
  body: string,
  commentWithinMs: number | null,
): Promise<string | undefined> {
  const label404 = await fetcher(`${API}/labels/${encodeURIComponent(label)}`, {
    headers: ghHeaders(token, false),
  });
  if (label404.status === 404) {
    await fetcher(`${API}/labels`, {
      method: "POST",
      headers: ghHeaders(token, true),
      body: JSON.stringify({ name: label, color }),
    });
  }
  if (commentWithinMs !== null) {
    const res = await fetcher(`${API}/issues?state=open&labels=${encodeURIComponent(label)}&per_page=100`, {
      headers: ghHeaders(token, false),
    });
    if (res.status === 200) {
      const open = ((await res.json()) as Array<{ number: number; created_at: string; html_url: string; pull_request?: unknown }>)
        .filter((i) => !i.pull_request);
      const recent = open.find((i) => Date.now() - Date.parse(i.created_at) < commentWithinMs);
      if (recent) {
        await fetcher(`${API}/issues/${recent.number}/comments`, {
          method: "POST",
          headers: ghHeaders(token, true),
          body: JSON.stringify({ body: `Another occurrence within the 24h window.\n\n${body}` }),
        });
        return recent.html_url;
      }
    }
  }
  const created = await fetcher(`${API}/issues`, {
    method: "POST",
    headers: ghHeaders(token, true),
    body: JSON.stringify({ title, body, labels: [label] }),
  });
  if (created.status !== 201) return undefined;
  return ((await created.json()) as { html_url?: string }).html_url;
}

/** Never throws. ok=false only when the alarm could not be filed. */
export async function runTwelvexWatch(
  which: TwelvexWatch,
  fetcher: GhFetch,
  token: string | undefined,
  nowMs: number,
): Promise<WatchOutcome> {
  try {
    if (which === "feed-confirm") {
      let runs: Run[] | null = null;
      try {
        runs = await listRuns(fetcher, token, "feed_published_confirm.yml", "event=workflow_dispatch&per_page=20");
      } catch {
        runs = null;
      }
      const v = evaluateFeedConfirm(nowMs, runs);
      if (!v.alarm) return { ok: true, alarm: false, detail: v.detail };
      const body = [
        "**The feed confirmation check did not run. Nothing is confirmed for the window that clock was supposed to cover.**",
        "",
        "Do not assume the feed is fine. Run the confirmation by hand and treat its exit code as the finding:",
        "",
        "```",
        "gh workflow run feed_published_confirm.yml --repo digithings-ai/twelve-x",
        "```",
        "",
        "Then check the clock: the `twelve-x-feed-confirm` row in digithings `apps/digithings-cron` (jobs.ts + wrangler.toml) and the Worker logs for that job id.",
        "",
        `Checked by digithings-cron (twelve-x-feed-confirm-watchdog) at ${new Date(nowMs).toISOString()}, looked back ${FEED_LOOKBACK_HOURS}h.`,
        "",
        "## What was observed",
        "",
        v.detail,
      ].join("\n");
      const url = await fileIssue(
        fetcher, token, FEED_LABEL, "d73a4a",
        "FX feed confirmation did not run — a trading date is unconfirmed", body, 86_400_000,
      );
      return { ok: url !== undefined, alarm: true, filed: url, detail: v.detail };
    }
    let runs: Run[] | null = null;
    try {
      runs = await listRuns(fetcher, token, heartbeatWorkflow(), "event=workflow_dispatch&per_page=1");
    } catch {
      runs = null;
    }
    const v = evaluateHeartbeat(nowMs, runs);
    if (!v.alarm) return { ok: true, alarm: false, detail: v.detail };
    const body = [
      "**The check did not run. No probe was performed.** The desk session credential is of **unknown** state — this is not an expiry verdict (that is the session-expired label).",
      "",
      `Evidence: ${v.detail}`,
      "",
      `The heartbeat is dispatched twice a day by digithings-cron; this fires when the last dispatch is older than ${HEARTBEAT_TOLERANCE_HOURS}h. Check the Worker first, then GH_DISPATCH_TOKEN's Actions:write grant on twelve-x, then whether the workflow is disabled.`,
      "",
      `Checked by digithings-cron (twelve-x-session-heartbeat-watchdog) at ${new Date(nowMs).toISOString()}.`,
    ].join("\n");
    const url = await fileIssue(
      fetcher, token, HB_LABEL, "fbca04",
      `Desk session heartbeat did not run — ${isoDay(nowMs)}`, body, null,
    );
    return { ok: url !== undefined, alarm: true, filed: url, detail: v.detail };
  } catch (err) {
    return { ok: false, alarm: false, detail: `watch_failed: ${err instanceof Error ? err.message : String(err)}` };
  }
}
