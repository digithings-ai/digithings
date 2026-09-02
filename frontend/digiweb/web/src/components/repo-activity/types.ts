/**
 * Snapshot-first repository activity — the shared data contract for compact
 * and detailed views. Velocity figures are windowed; backlog figures are not.
 * Stars, forks and watchers are deliberately absent.
 */

export type RepoRelease = {
  tag: string;
  name: string | null;
  publishedAt: string;
  url: string;
};

export type RepoPullItem = {
  number: number;
  title: string;
  url: string;
  /** Merge time when known; closed_at is an acceptable proxy from Search. */
  mergedAt: string | null;
};

export type RepoIssueItem = {
  number: number;
  title: string;
  url: string;
  updatedAt: string | null;
};

export type RepoFeature = {
  scope: string | null;
  summary: string;
  pr: number;
  date: string | null;
};

export type RepoModuleActivity = {
  path: string;
  lastCommit: string | null;
  files: number;
  lines: number;
};

/**
 * One snapshot object both variants render. `commits` / `pullsMerged` /
 * `issuesClosed` cover `windowDays` on `branch`. `pullsOpen` / `issuesOpen`
 * are the current backlog (unwindowed). `modules` and `features` are optional
 * extras for hosts that already generate them; the views do not require them.
 */
export type RepoActivitySnapshot = {
  generatedAt: string;
  windowDays: number;
  branch: string;
  commits: number;
  pullsMerged: number;
  issuesClosed: number;
  pullsOpen: number;
  issuesOpen: number;
  latestRelease: RepoRelease | null;
  mergedPulls: RepoPullItem[];
  openIssues: RepoIssueItem[];
  features?: RepoFeature[];
  modules?: Record<string, RepoModuleActivity | undefined>;
};

/** Live GitHub refresh — all-or-nothing; the component keeps the snapshot on any failure. */
export type RepoActivityLiveConfig = {
  owner: string;
  repo: string;
  branch?: string;
  windowDays?: number;
  timeoutMs?: number;
};

export const DEFAULT_LIVE_TIMEOUT_MS = 8_000;

/** `2026-08-06T12:34:56Z` → `2026-08-06`; empty string when absent. */
export function isoDay(stamp: string | null | undefined): string {
  return stamp ? stamp.slice(0, 10) : "";
}

/** Thousands-separated, locale-stable so SSR and the browser cannot drift. */
export function grouped(n: number): string {
  return n.toLocaleString("en-US");
}

/**
 * Split a clone command at its last slash so a `<wbr/>` can sit after the org.
 * Rejoining the halves must equal the copied payload.
 */
export function cloneParts(command: string): [string, string] {
  const cut = command.lastIndexOf("/") + 1;
  if (cut <= 0) return [command, ""];
  return [command.slice(0, cut), command.slice(cut)];
}
