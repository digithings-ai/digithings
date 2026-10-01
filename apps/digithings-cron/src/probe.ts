/**
 * Public GET probes for digithings-cron smoke jobs (#4761 CHR-E).
 * Site and stack checks run inside the Worker. They do not start a container
 * and they do not call api.github.com.
 */
export type ProbeKind = "site" | "stack";

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

export const STACK_HEALTH_URLS: readonly string[] = [
  "https://graph.digithings.ai/healthz",
  "https://key.digithings.ai/healthz",
  "https://search.digithings.ai/healthz",
];

export function probeUrls(kind: ProbeKind): string[] {
  switch (kind) {
    case "site":
      return [...SITE_ASSET_PROBES.map((row) => row.url), ...FRESHNESS_URLS];
    case "stack":
      return [...STACK_HEALTH_URLS];
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

async function fetchUrl(fetchImpl: ProbeFetch, url: string): Promise<{
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
    default: {
      const _never: never = kind;
      return _never;
    }
  }
}
