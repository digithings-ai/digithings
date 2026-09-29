/**
 * Fail-soft GitHub failure trackers for digiquant-runner (issue #4761).
 * Dedup is the body marker. A GitHub error must not change the job status.
 */
import type { FailureIssueSpec } from "./commands";
import type { Env } from "./env";
import type { RunRecord } from "./runner-session";

const GH_API = "https://api.github.com";
const GH_API_VERSION = "2022-11-28";
const REPO = "digithings-ai/digithings";
const MAX_LINES = 20;

type GhIssue = {
  number: number;
  body: string | null;
  pull_request?: unknown;
};

function headers(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": GH_API_VERSION,
    "Content-Type": "application/json",
    "User-Agent": "digiquant-runner",
  };
}

function nextLink(header: string | null): string | null {
  if (!header) return null;
  for (const part of header.split(",")) {
    const match = /<([^>]+)>;\s*rel="next"/.exec(part);
    if (match) return match[1];
  }
  return null;
}

async function listOpenIssues(token: string): Promise<GhIssue[]> {
  const found: GhIssue[] = [];
  let url: string | null = `${GH_API}/repos/${REPO}/issues?state=open&per_page=100`;
  while (url) {
    const res = await fetch(url, { headers: headers(token) });
    if (!res.ok) {
      throw new Error(`GitHub issues list failed: HTTP ${res.status}`);
    }
    const page = (await res.json()) as GhIssue[];
    for (const issue of page) {
      if (issue.pull_request) continue;
      found.push(issue);
    }
    url = nextLink(res.headers.get("Link"));
  }
  return found;
}

function failLine(run: RunRecord): string {
  const stamp = new Date().toISOString().slice(0, 10);
  return `- ${stamp} — run ${run.run_id} (${run.status})`;
}

function withLogTail(body: string, logTail: string): string {
  const clipped = logTail.split("\n").slice(-200).join("\n");
  return `${body}\n\n## Log tail\n\`\`\`\n${clipped}\n\`\`\``;
}

function updatedBody(existing: string, marker: string, title: string, run: RunRecord): string {
  const line = failLine(run);
  const parts = existing.split("## Recent failures");
  const header = (parts[0] || `${marker}\n`).trim();
  const tailRaw = (parts[1] || "").split("\n").filter((item) => item.startsWith("- "));
  const tail = [line, ...tailRaw].slice(0, MAX_LINES).join("\n");
  const body = `${header}\n\n## Recent failures (latest first)\n${tail}`;
  void title;
  return withLogTail(body, run.log_tail);
}

function createdBody(spec: FailureIssueSpec, run: RunRecord): string {
  const body = [
    spec.marker,
    `## Persistent tracker for ${spec.title}`,
    "",
    "This issue is updated on each failed run instead of opening new issues.",
    "",
    "## Recent failures (latest first)",
    failLine(run),
  ].join("\n");
  return withLogTail(body, run.log_tail);
}

export async function fileFailureIssue(
  env: Env,
  spec: FailureIssueSpec,
  run: RunRecord,
): Promise<void> {
  const token = env.GH_ISSUE_TOKEN;
  if (!token) {
    console.error(JSON.stringify({ error: "failure_issue", reason: "GH_ISSUE_TOKEN unset" }));
    return;
  }
  try {
    const open = await listOpenIssues(token);
    const tracker = open.find((issue) => (issue.body || "").includes(spec.marker));
    if (tracker) {
      const res = await fetch(`${GH_API}/repos/${REPO}/issues/${tracker.number}`, {
        method: "PATCH",
        headers: headers(token),
        body: JSON.stringify({
          body: updatedBody(tracker.body || spec.marker, spec.marker, spec.title, run),
        }),
      });
      if (!res.ok) {
        throw new Error(`GitHub issue update failed: HTTP ${res.status}`);
      }
      return;
    }
    const res = await fetch(`${GH_API}/repos/${REPO}/issues`, {
      method: "POST",
      headers: headers(token),
      body: JSON.stringify({
        title: spec.title,
        body: createdBody(spec, run),
        labels: spec.labels,
      }),
    });
    if (!res.ok) {
      throw new Error(`GitHub issue create failed: HTTP ${res.status}`);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(JSON.stringify({ error: "failure_issue", message }));
  }
}
