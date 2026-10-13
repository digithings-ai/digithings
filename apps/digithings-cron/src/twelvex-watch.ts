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
 *  - feed-confirm watchdog and PrimeMarket heartbeat watchdog: ports of
 *    feed_confirm_watchdog.yml and primarketet_heartbeat_watchdog.yml. Same
 *    labels, same thresholds, issues filed on digithings-ai/twelve-x.
 */
import { ghHeaders } from "./house-run-watch";

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

type Run = { status?: string; conclusion?: string | null; created_at?: string; html_url?: string; id?: number };

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
): GateVerdict {
  const { today, past } = daysToCheck(nowMs);
  const now = new Date(nowMs);
  const minute = now.getUTCHours() * 60 + now.getUTCMinutes();
  for (const [name, , slot] of SESSION_SLOTS) {
    const runs = runsBySession[name] ?? [];
    const on = (day: string) => runs.filter((r) => (r.created_at ?? "").slice(0, 10) === day);
    if (isWeekday(nowMs) && minute >= slot) {
      const covered = on(today).some(
        (r) => r.conclusion === "success" || PENDING.has(r.status ?? ""),
      );
      if (!covered) return { due: true, reason: `${name} not covered ${today}` };
    }
    for (const day of past) {
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
    return evaluateCatchup(nowMs, runsBySession);
  } catch (err) {
    return { due: true, reason: `gate_unreadable: ${err instanceof Error ? err.message : String(err)}` };
  }
}

// ---------------------------------------------------------------- watchdogs

export type TwelvexWatch = "feed-confirm" | "primemarket-heartbeat";
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
      runs = await listRuns(fetcher, token, "primemarket_session_heartbeat.yml", "event=workflow_dispatch&per_page=1");
    } catch {
      runs = null;
    }
    const v = evaluateHeartbeat(nowMs, runs);
    if (!v.alarm) return { ok: true, alarm: false, detail: v.detail };
    const body = [
      "**The check did not run. No probe was performed.** The desk session credential is of **unknown** state — this is not an expiry verdict (that is `primemarket-session-expired`).",
      "",
      `Evidence: ${v.detail}`,
      "",
      `The heartbeat is dispatched twice a day by digithings-cron; this fires when the last dispatch is older than ${HEARTBEAT_TOLERANCE_HOURS}h. Check the Worker first, then GH_DISPATCH_TOKEN's Actions:write grant on twelve-x, then whether the workflow is disabled.`,
      "",
      `Checked by digithings-cron (twelve-x-primemarket-heartbeat-watchdog) at ${new Date(nowMs).toISOString()}.`,
    ].join("\n");
    const url = await fileIssue(
      fetcher, token, HB_LABEL, "fbca04",
      `PrimeMarket heartbeat did not run — ${isoDay(nowMs)}`, body, null,
    );
    return { ok: url !== undefined, alarm: true, filed: url, detail: v.detail };
  } catch (err) {
    return { ok: false, alarm: false, detail: `watch_failed: ${err instanceof Error ? err.message : String(err)}` };
  }
}
