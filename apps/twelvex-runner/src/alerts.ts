/**
 * GitHub issue alerts that match the twelve-x workflow labels.
 * Ingest exit 2 stays quiet (the session heartbeat owns that alert).
 * Heartbeat exit 0 closes open primemarket-session-expired issues (DIG-2397).
 * Any other heartbeat failure files that label, including exit 2, because the
 * workflow step is `if: failure()` and does not split the exit codes.
 */

export const SOURCE_LABEL = "market-context-failure";
export const TRANSPORT_LABEL = "market-context-transport-failure";
export const SESSION_LABEL = "primemarket-session-expired";
export const WINDOW_MS = 24 * 60 * 60 * 1000;
export const HEARTBEAT_INTERVAL_MS = 12 * 60 * 60 * 1000;
export const REPO = "digithings-ai/twelve-x";
export const SESSION_OWNER = "chrizefan";

export type Route = "ingest" | "heartbeat";

export type OpenIssue = {
  number: number;
  createdAt: number;
  acknowledged: boolean;
};

export type AlertDecision =
  | { action: "none" }
  | {
      action: "create";
      label: string;
      title: string;
      body: string;
      assignees: string[];
      closeNumbers: number[];
    }
  | { action: "comment"; label: string; number: number; body: string; escalate: boolean }
  | { action: "close"; label: string; numbers: number[]; body: string };

export function labelFor(route: Route, exitCode: number): string | null {
  if (exitCode === 0) return null;
  if (route === "heartbeat") return SESSION_LABEL;
  if (exitCode === 2) return null;
  if (exitCode === 3) return TRANSPORT_LABEL;
  return SOURCE_LABEL;
}

export function verdictLine(logTail: string): string {
  const line = logTail.split("\n").find((row) => row.startsWith("MARKET_CONTEXT_VERDICT="));
  if (!line) return "no verdict line was recorded";
  return line.slice("MARKET_CONTEXT_VERDICT=".length).replace(/\s+/g, " ").slice(0, 400);
}

export function decideAlert(input: {
  route: Route;
  exitCode: number;
  bucket?: string;
  reason: string;
  now: number;
  open: OpenIssue[];
}): AlertDecision {
  if (input.route === "heartbeat" && input.exitCode === 0) {
    if (input.open.length === 0) return { action: "none" };
    return {
      action: "close",
      label: SESSION_LABEL,
      numbers: input.open.map((issue) => issue.number),
      body: [
        "Closed: the session probe passed.",
        "",
        "This occurrence is closed because the probe authenticated, not because a newer expiry arrived.",
      ].join("\n"),
    };
  }

  const label = labelFor(input.route, input.exitCode);
  if (!label) return { action: "none" };

  const fresh = input.open.find((issue) => input.now - issue.createdAt < WINDOW_MS);
  const day = new Date(input.now).toISOString().slice(0, 10);
  if (fresh) {
    const escalate =
      input.route === "heartbeat" &&
      !fresh.acknowledged &&
      input.now - fresh.createdAt >= HEARTBEAT_INTERVAL_MS;
    return {
      action: "comment",
      label,
      number: fresh.number,
      escalate,
      body: occurrenceBody(input, escalate),
    };
  }

  const title =
    input.route === "heartbeat"
      ? `PrimeMarket desk session expired — ${day}`
      : `Market context ingest failed — ${day}`;
  const closeNumbers =
    input.route === "ingest" ? input.open.map((issue) => issue.number) : [];
  return {
    action: "create",
    label,
    title,
    body: createBody(input),
    assignees: input.route === "heartbeat" ? [SESSION_OWNER] : [],
    closeNumbers,
  };
}

function occurrenceBody(
  input: { route: Route; exitCode: number; bucket?: string; reason: string },
  escalate: boolean,
): string {
  const lines = [
    `Another occurrence within the ${WINDOW_MS / 3600000}h window.`,
    `- Route: ${input.route}`,
    `- Exit code: ${input.exitCode}`,
    `- Reason: ${input.reason}`,
  ];
  if (input.bucket) lines.push(`- Bucket: ${input.bucket}`);
  if (escalate) {
    lines.push(
      "",
      `**Escalation: unread.** Owner: @${SESSION_OWNER}.`,
      "The desk session is still expired. Repair with ./scripts/refresh_session_token.sh.",
      "Any human comment on this thread stops the escalation.",
    );
  }
  return lines.join("\n");
}

function createBody(input: {
  route: Route;
  exitCode: number;
  bucket?: string;
  reason: string;
}): string {
  if (input.route === "heartbeat") {
    return [
      "The interim desk session (PRIMEMARKET_SESSION_TOKEN) is no longer valid.",
      "",
      "A human needs to sign in at the desk and run ./scripts/refresh_session_token.sh.",
      "See docs/PRIMEMARKET_DESK_API.md.",
      "",
      `- Exit code: ${input.exitCode}`,
      `- Reason: ${input.reason}`,
      "- Workflow: primemarket_session_heartbeat.yml",
    ].join("\n");
  }
  return [
    `The market-context ingest ('${input.bucket ?? "unknown"}' bucket) failed.`,
    "",
    `- Exit code: ${input.exitCode}`,
    `- Reason: ${input.reason}`,
    "- Workflow: market_context_ingest.yml",
  ].join("\n");
}

type GhIssue = {
  number: number;
  created_at: string;
  pull_request?: unknown;
  user?: { type?: string };
};

export async function loadOpen(
  token: string,
  label: string,
  fetchImpl: typeof fetch,
  now: number,
): Promise<OpenIssue[]> {
  const issues: OpenIssue[] = [];
  for (let page = 1; page <= 10; page += 1) {
    const url =
      `https://api.github.com/repos/${REPO}/issues?labels=${encodeURIComponent(label)}` +
      `&state=open&per_page=100&page=${page}`;
    const res = await fetchImpl(url, { headers: ghHeaders(token) });
    if (!res.ok) throw new Error(`github list issues HTTP ${res.status}`);
    const data = (await res.json()) as GhIssue[];
    for (const issue of data) {
      if (issue.pull_request) continue;
      const createdAt = Date.parse(issue.created_at);
      const acknowledged = await humanCommented(token, issue.number, fetchImpl);
      issues.push({
        number: issue.number,
        createdAt: Number.isFinite(createdAt) ? createdAt : now,
        acknowledged,
      });
    }
    if (data.length < 100) break;
  }
  return issues;
}

async function humanCommented(
  token: string,
  number: number,
  fetchImpl: typeof fetch,
): Promise<boolean> {
  const url = `https://api.github.com/repos/${REPO}/issues/${number}/comments?per_page=100`;
  const res = await fetchImpl(url, { headers: ghHeaders(token) });
  if (!res.ok) return false;
  const comments = (await res.json()) as { user?: { type?: string } }[];
  return comments.some((comment) => comment.user?.type && comment.user.type !== "Bot");
}

export async function executeAlert(
  token: string,
  decision: AlertDecision,
  fetchImpl: typeof fetch,
): Promise<void> {
  if (decision.action === "none") return;
  if (decision.action === "comment") {
    await postComment(token, decision.number, decision.body, fetchImpl);
    return;
  }
  if (decision.action === "close") {
    for (const number of decision.numbers) {
      await postComment(token, number, decision.body, fetchImpl);
      await patchIssue(token, number, { state: "closed", state_reason: "completed" }, fetchImpl);
    }
    return;
  }
  await ensureLabel(token, decision.label, fetchImpl);
  const created = await fetchImpl(`https://api.github.com/repos/${REPO}/issues`, {
    method: "POST",
    headers: ghHeaders(token),
    body: JSON.stringify({
      title: decision.title,
      body: decision.body,
      labels: [decision.label],
      assignees: decision.assignees,
    }),
  });
  if (!created.ok) throw new Error(`github create issue HTTP ${created.status}`);
  for (const number of decision.closeNumbers) {
    await patchIssue(token, number, { state: "closed", state_reason: "completed" }, fetchImpl);
  }
}

async function ensureLabel(token: string, label: string, fetchImpl: typeof fetch): Promise<void> {
  const existing = await fetchImpl(
    `https://api.github.com/repos/${REPO}/labels/${encodeURIComponent(label)}`,
    { headers: ghHeaders(token) },
  );
  if (existing.ok) return;
  const created = await fetchImpl(`https://api.github.com/repos/${REPO}/labels`, {
    method: "POST",
    headers: ghHeaders(token),
    body: JSON.stringify({
      name: label,
      color: "d73a4a",
      description:
        label === TRANSPORT_LABEL
          ? "Automated alert: the desk was unreachable (ingest exit 3)"
          : label === SESSION_LABEL
            ? "Automated alert: the interim desk session has expired"
            : "Automated alert: market-context ingest failed",
    }),
  });
  if (!created.ok && created.status !== 422) {
    throw new Error(`github create label HTTP ${created.status}`);
  }
}

async function postComment(
  token: string,
  number: number,
  body: string,
  fetchImpl: typeof fetch,
): Promise<void> {
  const res = await fetchImpl(
    `https://api.github.com/repos/${REPO}/issues/${number}/comments`,
    {
      method: "POST",
      headers: ghHeaders(token),
      body: JSON.stringify({ body }),
    },
  );
  if (!res.ok) throw new Error(`github comment HTTP ${res.status}`);
}

async function patchIssue(
  token: string,
  number: number,
  body: Record<string, string>,
  fetchImpl: typeof fetch,
): Promise<void> {
  const res = await fetchImpl(`https://api.github.com/repos/${REPO}/issues/${number}`, {
    method: "PATCH",
    headers: ghHeaders(token),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`github patch issue HTTP ${res.status}`);
}

function ghHeaders(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "Content-Type": "application/json",
    "User-Agent": "twelvex-runner",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}
