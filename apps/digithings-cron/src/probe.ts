/**
 * Public GET probes for digithings-cron smoke jobs (#4761 CHR-E).
 * Site and stack checks run inside the Worker. They do not start a container
 * and they do not call api.github.com.
 */
export type ProbeKind = "site" | "stack" | "deploy";

export type FreshnessLabel =
  | "WARN"
  | "UNSTAMPED"
  | "UNREACHABLE"
  | "MALFORMED"
  | "STALE"
  | "PASS";

export type FreshnessVerdict = {
  label: FreshnessLabel;
  failed: boolean;
  message: string;
};

export type ProbeFetch = (input: string, init?: RequestInit) => Promise<Response>;

/** Same agent the smoke-site.yml curl steps send. */
export const PROBE_USER_AGENT =
  "digithings-site-smoke/1.0 (+https://github.com/digithings-ai/digithings)";

const PROBE_TIMEOUT_MS = 20_000;

/** 403 / 429 match the workflow bot-challenge rule. Status 0 is no response. */
const INCONCLUSIVE_STATUSES = new Set([0, 403, 429]);

/** Asset probes treat status 0 as FAIL. Freshness treats it as WARN. */
const ASSET_WARN_STATUSES = new Set([403, 429]);

const OK_STATUSES = new Set([200, 206]);

const MAX_FUTURE_SKEW_HOURS = 24;
const MAX_AGE_HOURS = 168;

export const SITE_ASSET_PROBES: readonly { url: string; contentType: string }[] = [
  { url: "https://digithings.ai/", contentType: "text/html" },
  { url: "https://digithings.ai/docs/", contentType: "text/html" },
  { url: "https://digithings.ai/openwiki/", contentType: "text/html" },
  { url: "https://digithings.ai/openwiki/graph.json", contentType: "application/json" },
  { url: "https://digithings.ai/og.png", contentType: "image/png" },
  { url: "https://digiquant.io/", contentType: "text/html" },
  { url: "https://digiquant.io/dashboard/", contentType: "text/html" },
  { url: "https://digiquant.io/og.png", contentType: "image/png" },
];

export const FRESHNESS_URLS: readonly string[] = [
  "https://digiquant.io/build-info.json",
  "https://digithings.ai/build-info.json",
];

// Worker-only status (cost epic): /_stack/status is answered by the stack Worker
// without waking the 6 GiB container. Container health is checked from the Mac.
export const STACK_HEALTH_URLS: readonly string[] = [
  "https://graph.digithings.ai/_stack/status",
  "https://key.digithings.ai/_stack/status",
  "https://search.digithings.ai/_stack/status",
];

/* --------------------------------------------------------------------------
 * Deploy freshness (DIG-4871): "main moved, production did not".
 *
 * The daily site probe reads the stamp's AGE only (168h limit), so a broken
 * deploy path stayed green for 7.8 days: digiquant.io served the 2026-10-13
 * build while main had moved on. This probe reads the same stamp and asks a
 * different question - does the live commit equal the production branch tip?
 *
 * Expected-commit source: the repository's PUBLIC git remote, read over the
 * git smart-HTTP transport - exactly what `git ls-remote` reads:
 *
 *   GET https://github.com/digithings-ai/digithings/info/refs?service=git-upload-pack
 *
 * The ref advertisement carries `refs/heads/main -> sha`. No api.github.com
 * call, no token, no Contents grant - so it runs from the Worker, whose
 * Actions token carries none of those.
 *
 * Anchor source: the public commit feed of the same branch,
 * `https://github.com/digithings-ai/digithings/commits/main.atom`. It says
 * when main moved, not only where it is: the feed is newest first, so the
 * entry just before the served commit is the first commit production missed.
 * That is the start of the break and the anchor of the in-flight grace.
 * ----------------------------------------------------------------------- */

/** Live production stamp of the site under watch (Cloudflare Pages, ADR-0012). */
export const DEPLOY_SITE_URL = "https://digiquant.io/build-info.json";

/** The production branch digiquant.io is built from (ADR-0012). */
export const DEPLOY_BRANCH = "main";

/** Public ref advertisement of the repository's git remote. */
export const DEPLOY_REMOTE_REFS_URL =
  "https://github.com/digithings-ai/digithings/info/refs?service=git-upload-pack";

/**
 * Anchor for the in-flight grace: the public patch of that exact sha. The
 * mbox header carries the commit date, and the patch is fetched BY sha, so
 * the date can never belong to a different commit. Used only when the commit
 * feed cannot name the anchor.
 */
export const DEPLOY_COMMIT_PATCH_URL =
  "https://github.com/digithings-ai/digithings/commit";

/**
 * The commit feed of the production branch: public, no token, no
 * api.github.com. It answers the question the tip alone cannot answer:
 * WHEN did main first move past the commit production serves?
 *
 * The feed is the anchor source because the tip moves often (promotions land
 * every few hours here). A grace anchored on the tip restarts on every main
 * move, so a 36 hour deploy break was masked by a main move 6 minutes ago.
 * The feed is newest first, so the entry just before the served commit is the
 * first commit production missed - the moment the break started.
 */
export const DEPLOY_REMOTE_FEED_URL =
  "https://github.com/digithings-ai/digithings/commits/main.atom";

/**
 * Grace for a Pages build that may still be in flight.
 *
 * Measured on the real stamps: production was written 3m08s after its commit,
 * a preview build 7m03s after its commit. Six hours is ~50x the real build,
 * and it absorbs a promotion PR that sat open for hours before it merged.
 */
export const DEPLOY_GRACE_HOURS = 6;

export type DeployLabel = "PASS" | "WARN" | "FAIL";

export type DeployVerdict = {
  label: DeployLabel;
  failed: boolean;
  message: string;
};

/** What the live site serves. */
export type DeployStamp = {
  /** commit in the live build stamp, or null when the stamp carries none. */
  commit: string | null;
  /** built_at in the live build stamp, or null. */
  builtAt: string | null;
  /** why the stamp is missing or unreadable, for the message. */
  detail: string;
};

/** One commit of the public production-branch feed. */
export type DeployFeedEntry = {
  /** commit sha. */
  sha: string;
  /** when the commit landed (ISO 8601). */
  updated: string;
};

/** What production is expected to serve. */
export type DeployExpectation = {
  /** sha of the production branch tip, read from the public git remote. */
  commit: string | null;
  /** when that tip landed (ISO 8601), or null when it could not be read. */
  committedAt: string | null;
  /**
   * sha of the oldest production-branch commit production has not built, or
   * null when it could not be identified. This is the anchor of the grace:
   * the moment main first moved past what production serves.
   */
  unbuiltCommit: string | null;
  /** when that commit landed (ISO 8601), or null. */
  unbuiltAt: string | null;
};

export function probeUrls(kind: ProbeKind): string[] {
  switch (kind) {
    case "site":
      return [...SITE_ASSET_PROBES.map((row) => row.url), ...FRESHNESS_URLS];
    case "stack":
      return [...STACK_HEALTH_URLS];
    case "deploy":
      return [DEPLOY_SITE_URL, DEPLOY_REMOTE_REFS_URL, DEPLOY_REMOTE_FEED_URL];
    default: {
      const _never: never = kind;
      return _never;
    }
  }
}

function parseBuiltAt(raw: string): Date | null {
  const text = raw.trim();
  if (!text) return null;
  const withZone = /(?:[zZ]|[+-]\d{2}:\d{2})$/.test(text) ? text : `${text}Z`;
  const ms = Date.parse(withZone);
  if (Number.isNaN(ms)) return null;
  return new Date(ms);
}

function formatUtc(date: Date): string {
  return date.toISOString().replace(/\.\d{3}Z$/, "Z");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Port of scripts/check_deploy_freshness.py evaluate().
 * max age 168h. A stamp more than 24h in the future is MALFORMED.
 */
export function evaluateFreshness(
  url: string,
  status: number,
  body: string,
  now: Date,
): FreshnessVerdict {
  if (INCONCLUSIVE_STATUSES.has(status)) {
    return {
      label: "WARN",
      failed: false,
      message: `${url} -> HTTP ${status} (bot challenge or no response; inconclusive from CI)`,
    };
  }
  if (status === 404) {
    return {
      label: "UNSTAMPED",
      failed: true,
      message:
        `${url} -> HTTP 404: the live deploy predates the build stamp, so it is ` +
        "older than the commit that added build-info.json (see #1759)",
    };
  }
  if (!OK_STATUSES.has(status)) {
    return {
      label: "UNREACHABLE",
      failed: true,
      message: `${url} -> HTTP ${status}`,
    };
  }

  let payload: unknown;
  try {
    payload = JSON.parse(body) as unknown;
  } catch {
    return {
      label: "UNSTAMPED",
      failed: true,
      message:
        `${url} -> HTTP ${status} but the body is not JSON: the live deploy has no ` +
        "build stamp (SPA fallback), so it predates build-info.json (see #1759)",
    };
  }
  if (!isRecord(payload)) {
    return {
      label: "MALFORMED",
      failed: true,
      message: `${url} -> JSON body is not an object: ${JSON.stringify(body).slice(0, 120)}`,
    };
  }

  const rawBuiltAt = payload.built_at;
  const builtAt = typeof rawBuiltAt === "string" ? parseBuiltAt(rawBuiltAt) : null;
  if (builtAt === null) {
    return {
      label: "MALFORMED",
      failed: true,
      message: `${url} -> stamp has no parseable 'built_at' (got ${JSON.stringify(rawBuiltAt)})`,
    };
  }

  const identity = ["site", "branch", "commit", "builder"]
    .filter((field) => payload[field])
    .map((field) => `${field}=${String(payload[field])}`)
    .join(" ");
  const ageHours = (now.getTime() - builtAt.getTime()) / 3_600_000;
  const detail =
    `built_at=${formatUtc(builtAt)} age=${(ageHours / 24).toFixed(1)}d ${identity}`.trimEnd();

  if (ageHours < -MAX_FUTURE_SKEW_HOURS) {
    return {
      label: "MALFORMED",
      failed: true,
      message: `${url} -> stamp is dated ${(-ageHours / 24).toFixed(1)}d in the future; ${detail}`,
    };
  }
  if (ageHours > MAX_AGE_HOURS) {
    return {
      label: "STALE",
      failed: true,
      message:
        `${url} -> no deploy for ${(ageHours / 24).toFixed(1)}d ` +
        `(limit ${(MAX_AGE_HOURS / 24).toFixed(1)}d); ${detail}`,
    };
  }
  return { label: "PASS", failed: false, message: `${url} -> ${detail}` };
}

type Check = { url: string; failed: boolean; message: string };

function logCheck(check: Check): void {
  console.log(
    JSON.stringify({
      probe_url: check.url,
      failed: check.failed,
      message: check.message,
    }),
  );
}

async function fetchUrl(
  fetchImpl: ProbeFetch,
  url: string,
  extraHeaders?: Record<string, string>,
): Promise<{
  status: number;
  contentType: string;
  body: string;
}> {
  try {
    const res = await fetchImpl(url, {
      method: "GET",
      redirect: "follow",
      headers: {
        "User-Agent": PROBE_USER_AGENT,
        Accept: "*/*",
        ...(extraHeaders ?? {}),
      },
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    });
    const body = await res.text();
    return {
      status: res.status,
      contentType: res.headers.get("content-type") ?? "",
      body,
    };
  } catch {
    return { status: 0, contentType: "", body: "" };
  }
}

function evaluateAsset(url: string, wantType: string, status: number, contentType: string): Check {
  if (status === 200) {
    if (contentType.includes(wantType)) {
      return { url, failed: false, message: `PASS  ${url} (${contentType})` };
    }
    if (contentType.includes("text/html") && wantType !== "text/html") {
      return {
        url,
        failed: true,
        message: `FAIL  ${url} returned text/html — SPA fallback is masking a missing asset`,
      };
    }
    return {
      url,
      failed: true,
      message: `FAIL  ${url} returned unexpected content-type '${contentType}' (wanted ${wantType})`,
    };
  }
  if (ASSET_WARN_STATUSES.has(status)) {
    return {
      url,
      failed: false,
      message: `WARN  ${url} -> ${status} (bot challenge; inconclusive from CI)`,
    };
  }
  return { url, failed: true, message: `FAIL  ${url} -> HTTP ${status}` };
}

function evaluateStack(url: string, status: number, body: string): Check {
  if (ASSET_WARN_STATUSES.has(status)) {
    return {
      url,
      failed: false,
      message: `WARN  ${url} -> ${status} (bot challenge; inconclusive from CI)`,
    };
  }
  if (status !== 200) {
    return { url, failed: true, message: `FAIL  ${url} -> HTTP ${status}` };
  }
  try {
    const payload = JSON.parse(body) as unknown;
    if (isRecord(payload) && payload.ok === true) {
      return { url, failed: false, message: `PASS  ${url}` };
    }
  } catch {
    // Non-JSON 200 fails below.
  }
  return { url, failed: true, message: `FAIL  ${url} -> healthz ok is not true` };
}

/* --- Deploy freshness (DIG-4871) ----------------------------------------- */

/** RFC 2822 offset without a colon ("+0200") -> the ES Date.parse form ("+02:00"). */
const RFC2822_OFFSET = /([+-]\d{2})(\d{2})$/;

function parseRfc2822Date(raw: string): Date | null {
  const ms = Date.parse(raw.trim().replace(RFC2822_OFFSET, "$1:$2"));
  return Number.isNaN(ms) ? null : new Date(ms);
}

/**
 * sha of `refs/heads/main` in a git ref advertisement (pkt-line).
 *
 * Advertisement lines read `<40-hex sha> <ref name>`, so the sha sits right
 * before the ref name: the parser looks backwards from the name instead of
 * walking the pkt-line framing, which a truncated body may cut in half.
 */
export function parseRemoteRef(body: string, ref: string = DEPLOY_BRANCH): string | null {
  const marker = `refs/heads/${ref}`;
  const idx = body.indexOf(marker);
  if (idx < 0) return null;
  const next = body[idx + marker.length];
  // "refs/heads/main" must not be the prefix of a longer ref name.
  if (next !== undefined && /[A-Za-z0-9._\-/]/.test(next)) return null;
  const before = body.slice(Math.max(0, idx - 64), idx);
  const match = /([0-9a-f]{40})\s*$/.exec(before);
  return match ? match[1] : null;
}

/**
 * Commit date from the mbox header of a commit patch.
 *
 * `Date: Thu, 22 Oct 2026 01:59:00 +0200` - the author's date. On main that
 * is minutes away from the merge (main only moves by promotion PR), so it
 * says when main moved.
 */
export function parseCommitPatchDate(body: string): string | null {
  const match = /^Date:[ \t]*(.+)$/m.exec(body);
  if (!match) return null;
  const parsed = parseRfc2822Date(match[1]);
  return parsed ? formatUtc(parsed) : null;
}

function formatAge(ageHours: number): string {
  return ageHours >= 48 ? `${(ageHours / 24).toFixed(1)}d` : `${ageHours.toFixed(1)}h`;
}

/**
 * Commits of the production branch from the public atom feed, newest first.
 *
 * Every entry carries the commit sha and the commit date, so the feed says
 * not only what main is at but when it got there. The feed is public: no
 * token, no api.github.com, no Contents grant.
 */
export function parseCommitFeed(body: string): DeployFeedEntry[] {
  const entries: DeployFeedEntry[] = [];
  const blocks = body.match(/<entry>[\s\S]*?<\/entry>/g) ?? [];
  for (const block of blocks) {
    const sha = /Grit::Commit\/([0-9a-f]{40})/.exec(block);
    const updated = /<updated>([^<]+)<\/updated>/.exec(block);
    if (!sha || !updated) continue;
    entries.push({ sha: sha[1], updated: updated[1].trim() });
  }
  return entries;
}

/**
 * The oldest production-branch commit production has not built - the moment
 * main first moved past what production serves.
 *
 * The feed is newest first, so the entry just before the served commit in
 * that order is the first commit production missed. When the served commit
 * has fallen out of the feed window, the oldest entry newer than the served
 * build time is the best visible anchor: it is older than the truth, so the
 * probe stays conservative and never fails early.
 */
export function oldestUnbuiltCommit(
  feed: DeployFeedEntry[],
  servedSha: string | null,
  servedBuiltAt: string | null,
): DeployFeedEntry | null {
  if (feed.length === 0) return null;
  const index = servedSha ? feed.findIndex((entry) => entry.sha === servedSha) : -1;
  if (index >= 0) {
    // The served commit is the newest entry: nothing in the feed is newer.
    return index === 0 ? null : feed[index - 1];
  }
  if (servedBuiltAt) {
    const built = parseBuiltAt(servedBuiltAt);
    if (built) {
      const newer = feed.filter((entry) => {
        const at = parseBuiltAt(entry.updated);
        return at !== null && at.getTime() > built.getTime();
      });
      if (newer.length > 0) return newer[newer.length - 1];
    }
  }
  return null;
}

/**
 * The rule: production must serve the production branch tip.
 *
 * Deliberately asymmetric. This probe never fails on its own transport (an
 * unreadable remote is WARN, not FAIL) and never fails on a missing stamp
 * (the site probe owns that). It fails on exactly one signal, the one the
 * age probe cannot see: main moved, production did not.
 */
export function evaluateDeployCommit(
  stamp: DeployStamp,
  expectation: DeployExpectation,
  now: Date,
  graceHours: number = DEPLOY_GRACE_HOURS,
): DeployVerdict {
  const expected = expectation.commit;
  const served = stamp.commit;

  if (!expected) {
    return {
      label: "WARN",
      failed: false,
      message:
        `digiquant.io deploy check -> could not read ${DEPLOY_BRANCH} from the public git remote ` +
        "(refs advertisement); the expected commit is unknown, so this run decides nothing",
    };
  }
  if (!served) {
    return {
      label: "WARN",
      failed: false,
      message:
        `digiquant.io deploy check -> the live build stamp carries no commit (${stamp.detail}); ` +
        `${DEPLOY_BRANCH} is ${expected}. The site probe owns the missing-stamp signal`,
    };
  }
  if (served === expected) {
    return {
      label: "PASS",
      failed: false,
      message:
        `digiquant.io deploy check -> production serves ${DEPLOY_BRANCH} HEAD ${expected} ` +
        `(built at ${stamp.builtAt ?? "unknown"})`,
    };
  }
  if (!expectation.unbuiltCommit && !expectation.committedAt) {
    return {
      label: "WARN",
      failed: false,
      message:
        `digiquant.io deploy check -> production serves ${served} but ${DEPLOY_BRANCH} is ${expected}; ` +
        "the commit date is unknown, so a build may still be in flight",
    };
  }
  // The anchor of the grace: when main first moved past what production
  // serves. The tip date is only a fallback - a tip that moved minutes ago
  // would restart the grace and mask a break that started days earlier.
  const anchorCommit = expectation.unbuiltCommit ?? expected;
  const anchorAt = expectation.unbuiltAt ?? expectation.committedAt;
  const movedAt = anchorAt ? parseBuiltAt(anchorAt) : null;
  if (movedAt === null) {
    return {
      label: "WARN",
      failed: false,
      message:
        `digiquant.io deploy check -> the commit date "${anchorAt}" of ${anchorCommit} is not a date; ` +
        `production serves ${served}`,
    };
  }
  const ageHours = (now.getTime() - movedAt.getTime()) / 3_600_000;
  if (ageHours <= graceHours) {
    return {
      label: "WARN",
      failed: false,
      message:
        `digiquant.io deploy check -> ${DEPLOY_BRANCH} moved to ${anchorCommit} ${formatAge(ageHours)} ago ` +
        `(grace ${graceHours}h) and production still serves ${served}; a Pages build may still be in flight`,
    };
  }
  return {
    label: "FAIL",
    failed: true,
    message:
      `digiquant.io deploy check -> ${DEPLOY_BRANCH} moved to ${anchorCommit} at ${formatUtc(movedAt)} ` +
      `(${formatAge(ageHours)} ago) but digiquant.io still serves ${served} built at ` +
      `${stamp.builtAt ?? "unknown"}`,
  };
}

async function readProductionStamp(fetchImpl: ProbeFetch): Promise<DeployStamp> {
  const fetched = await fetchUrl(fetchImpl, DEPLOY_SITE_URL);
  if (!OK_STATUSES.has(fetched.status)) {
    return { commit: null, builtAt: null, detail: `HTTP ${fetched.status}` };
  }
  let payload: unknown;
  try {
    payload = JSON.parse(fetched.body) as unknown;
  } catch {
    return { commit: null, builtAt: null, detail: "the body is not JSON" };
  }
  if (!isRecord(payload)) {
    return { commit: null, builtAt: null, detail: "the body is not an object" };
  }
  const commit = typeof payload.commit === "string" && payload.commit ? payload.commit : null;
  const builtAt = typeof payload.built_at === "string" && payload.built_at ? payload.built_at : null;
  return {
    commit,
    builtAt,
    detail: commit ? `built_at=${builtAt ?? "unknown"}` : "the stamp carries no commit",
  };
}

async function readExpectedCommit(fetchImpl: ProbeFetch): Promise<string | null> {
  const fetched = await fetchUrl(fetchImpl, DEPLOY_REMOTE_REFS_URL);
  if (!OK_STATUSES.has(fetched.status)) return null;
  return parseRemoteRef(fetched.body);
}

async function readCommitDate(fetchImpl: ProbeFetch, sha: string): Promise<string | null> {
  const fetched = await fetchUrl(fetchImpl, `${DEPLOY_COMMIT_PATCH_URL}/${sha}.patch`, {
    Range: "bytes=0-1023",
  });
  if (!OK_STATUSES.has(fetched.status)) return null;
  return parseCommitPatchDate(fetched.body);
}

async function readCommitFeed(fetchImpl: ProbeFetch): Promise<DeployFeedEntry[]> {
  const fetched = await fetchUrl(fetchImpl, DEPLOY_REMOTE_FEED_URL);
  if (!OK_STATUSES.has(fetched.status)) return [];
  return parseCommitFeed(fetched.body);
}

async function runChecks(checks: Check[]): Promise<{ ok: true }> {
  const failed = checks.filter((check) => check.failed);
  for (const check of checks) logCheck(check);
  if (failed.length > 0) {
    throw new Error(failed[0].message);
  }
  return { ok: true };
}

export async function runSiteProbe(fetchImpl: ProbeFetch, now: Date): Promise<{ ok: true }> {
  const checks: Check[] = [];
  for (const row of SITE_ASSET_PROBES) {
    const fetched = await fetchUrl(fetchImpl, row.url);
    checks.push(evaluateAsset(row.url, row.contentType, fetched.status, fetched.contentType));
  }
  for (const url of FRESHNESS_URLS) {
    const fetched = await fetchUrl(fetchImpl, url);
    const verdict = evaluateFreshness(url, fetched.status, fetched.body, now);
    checks.push({ url, failed: verdict.failed, message: verdict.message });
  }
  return runChecks(checks);
}

export async function runStackProbe(fetchImpl: ProbeFetch): Promise<{ ok: true }> {
  const checks: Check[] = [];
  for (const url of STACK_HEALTH_URLS) {
    const fetched = await fetchUrl(fetchImpl, url);
    checks.push(evaluateStack(url, fetched.status, fetched.body));
  }
  return runChecks(checks);
}

/**
 * Deploy freshness (DIG-4871): does production serve the production branch
 * tip? Fails within hours of main moving without a deploy, instead of the
 * 7.8 days the age-only probe needed.
 */
export async function runDeployProbe(fetchImpl: ProbeFetch, now: Date): Promise<{ ok: true }> {
  const stamp = await readProductionStamp(fetchImpl);
  const expected = await readExpectedCommit(fetchImpl);
  let committedAt: string | null = null;
  let unbuiltCommit: string | null = null;
  let unbuiltAt: string | null = null;
  if (expected && stamp.commit && expected !== stamp.commit) {
    // The feed names the commit production missed first, so the grace is
    // anchored on the start of the break and not on the last main move.
    const feed = await readCommitFeed(fetchImpl);
    const anchor = oldestUnbuiltCommit(feed, stamp.commit, stamp.builtAt);
    if (anchor) {
      unbuiltCommit = anchor.sha;
      unbuiltAt = anchor.updated;
    } else {
      // No anchor in the feed (unreadable, or the served commit is not on
      // the branch): fall back to the date of the tip itself. Degraded mode -
      // a tip that moved inside the grace keeps the row WARN.
      committedAt = await readCommitDate(fetchImpl, expected);
    }
  }
  const verdict = evaluateDeployCommit(
    stamp,
    { commit: expected, committedAt, unbuiltCommit, unbuiltAt },
    now,
  );
  return runChecks([
    { url: DEPLOY_SITE_URL, failed: verdict.failed, message: verdict.message },
  ]);
}

export async function runProbe(
  kind: ProbeKind,
  fetchImpl: ProbeFetch,
  now: Date,
): Promise<{ ok: true }> {
  switch (kind) {
    case "site":
      return runSiteProbe(fetchImpl, now);
    case "stack":
      return runStackProbe(fetchImpl);
    case "deploy":
      return runDeployProbe(fetchImpl, now);
    default: {
      const _never: never = kind;
      return _never;
    }
  }
}
