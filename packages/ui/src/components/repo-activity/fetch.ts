/**
 * Unauthenticated GitHub refresh for repository activity.
 *
 * All requests must succeed and validate before a result is returned. The
 * caller (RepoActivity) applies that result atomically or keeps the snapshot.
 * Commits are counted on the configured branch via the Link last-page trick
 * (per_page=1); Search supplies the four issue/PR totals plus list rows.
 * `/repos/{owner}/{repo}` is never fetched — that payload carries stars/forks.
 */

import {
  DEFAULT_LIVE_TIMEOUT_MS,
  type RepoActivityLiveConfig,
  type RepoActivitySnapshot,
  type RepoIssueItem,
  type RepoPullItem,
  type RepoRelease,
} from "./types";

export type FetchRepoActivityLiveOptions = RepoActivityLiveConfig & {
  fetch?: typeof globalThis.fetch;
  now?: () => Date;
};

type LiveResult = Omit<RepoActivitySnapshot, "features" | "modules">;

const API = "https://api.github.com";

export async function fetchRepoActivityLive(
  options: FetchRepoActivityLiveOptions,
): Promise<LiveResult> {
  const owner = options.owner.trim();
  const repo = options.repo.trim();
  if (!/^[A-Za-z0-9_.-]+$/.test(owner) || !/^[A-Za-z0-9_.-]+$/.test(repo)) {
    throw new Error("malformed repo activity: invalid owner/repo");
  }
  const branch = options.branch?.trim() || "main";
  const windowDays = options.windowDays ?? 30;
  const timeoutMs = options.timeoutMs ?? DEFAULT_LIVE_TIMEOUT_MS;
  const fetchFn = options.fetch ?? globalThis.fetch;
  const now = options.now ?? (() => new Date());
  const generatedAt = toIsoZ(now());
  const since = new Date(Date.parse(generatedAt) - windowDays * 86_400_000);
  const sinceIso = toIsoZ(since);
  const sinceDay = sinceIso.slice(0, 10);
  const slug = `${owner}/${repo}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const get = (path: string) =>
    fetchJson(fetchFn, `${API}${path}`, controller.signal);

  try {
    const [commitsRes, merged, closed, openPrs, openIssues, releases] = await Promise.all([
      get(`/repos/${slug}/commits?sha=${encodeURIComponent(branch)}&since=${sinceIso}&per_page=1`),
      get(
        `/search/issues?q=repo:${slug}+is:pr+is:merged+merged:>=${sinceDay}&per_page=6&sort=updated`,
      ),
      get(`/search/issues?q=repo:${slug}+is:issue+is:closed+closed:>=${sinceDay}&per_page=1`),
      get(`/search/issues?q=repo:${slug}+is:pr+is:open&per_page=1`),
      get(`/search/issues?q=repo:${slug}+is:issue+is:open&per_page=6&sort=updated`),
      get(`/repos/${slug}/releases?per_page=1`),
    ]);

    return {
      generatedAt,
      windowDays,
      branch,
      commits: commitCount(commitsRes),
      pullsMerged: searchTotal(merged.body),
      issuesClosed: searchTotal(closed.body),
      pullsOpen: searchTotal(openPrs.body),
      issuesOpen: searchTotal(openIssues.body),
      latestRelease: parseLatestRelease(releases.body),
      mergedPulls: parsePullItems(merged.body),
      openIssues: parseIssueItems(openIssues.body),
    };
  } catch (err) {
    if (isAbort(err)) throw new Error("repo activity timeout");
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

type Fetched = { body: unknown; headers: Headers };

async function fetchJson(
  fetchFn: typeof globalThis.fetch,
  url: string,
  signal: AbortSignal,
): Promise<Fetched> {
  let res: Response;
  try {
    res = await fetchFn(url, { signal });
  } catch (err) {
    if (isAbort(err)) throw new Error("repo activity timeout");
    throw err;
  }
  if (!res.ok) {
    throw new Error(`repo activity HTTP ${res.status}`);
  }
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new Error("malformed repo activity");
  }
  return { body, headers: res.headers };
}

function commitCount(res: Fetched): number {
  const last = lastPage(res.headers.get("Link") ?? res.headers.get("link"));
  if (last != null) return last;
  if (!Array.isArray(res.body)) throw new Error("malformed repo activity");
  return res.body.length;
}

function lastPage(link: string | null): number | null {
  if (!link) return null;
  for (const part of link.split(",")) {
    if (!part.includes('rel="last"')) continue;
    const m = /[?&]page=(\d+)/.exec(part);
    if (m) return Number(m[1]);
  }
  return null;
}

function searchTotal(body: unknown): number {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new Error("malformed repo activity");
  }
  const count = (body as { total_count?: unknown }).total_count;
  return intCount(count);
}

function parsePullItems(body: unknown): RepoPullItem[] {
  return searchItems(body).map((item) => ({
    number: intCount(item.number, { min: 1 }),
    title: str(item.title),
    url: githubUrl(item.html_url),
    mergedAt: stamp(item.closed_at) ?? stamp(item.updated_at),
  }));
}

function parseIssueItems(body: unknown): RepoIssueItem[] {
  return searchItems(body).map((item) => ({
    number: intCount(item.number, { min: 1 }),
    title: str(item.title),
    url: githubUrl(item.html_url),
    updatedAt: stamp(item.updated_at),
  }));
}

function searchItems(body: unknown): Record<string, unknown>[] {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new Error("malformed repo activity");
  }
  const items = (body as { items?: unknown }).items;
  if (items == null) return [];
  if (!Array.isArray(items)) throw new Error("malformed repo activity");
  return items.filter((it): it is Record<string, unknown> => !!it && typeof it === "object");
}

function parseLatestRelease(body: unknown): RepoRelease | null {
  if (!Array.isArray(body)) throw new Error("malformed repo activity");
  const first = body[0];
  if (!first || typeof first !== "object") return null;
  const row = first as Record<string, unknown>;
  return {
    tag: str(row.tag_name),
    name: row.name == null ? null : str(row.name),
    publishedAt: str(row.published_at),
    url: githubUrl(row.html_url),
  };
}

function intCount(v: unknown, opts: { min?: number } = {}): number {
  if (typeof v !== "number" || !Number.isInteger(v) || !Number.isFinite(v) || v < (opts.min ?? 0)) {
    throw new Error("malformed repo activity");
  }
  return v;
}

function str(v: unknown): string {
  if (typeof v !== "string" || !v.trim()) throw new Error("malformed repo activity");
  return v;
}

function githubUrl(v: unknown): string {
  const url = str(v);
  if (!url.startsWith("https://github.com/")) throw new Error("malformed repo activity");
  return url;
}

function stamp(v: unknown): string | null {
  if (v == null) return null;
  if (typeof v !== "string") throw new Error("malformed repo activity");
  return v;
}

function toIsoZ(d: Date): string {
  return d.toISOString().replace(/\.\d{3}Z$/, "Z");
}

function isAbort(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && (err.name === "AbortError" || /aborted/i.test(err.message)))
  );
}
