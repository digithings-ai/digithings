/**
 * Retired operator URLs under /dashboard map onto the live desk.
 * /dashboard and /dashboard/ are the brief (/app). A known desk path uses the
 * same trailing-slash shape as deskHref. Retired dashboard pages with no desk
 * twin go to /app. There is no catch-all: the account pages (login, signup,
 * Auth callback, settings, Alpaca OAuth callback) still ship from apps/dashboard
 * under /dashboard and are pinned by Supabase Edge Functions (app-url.ts),
 * Stripe returns and scripts/build-digiquant.sh. A splat would shadow them.
 *
 * Keep LEGACY_DESK_PATHS equal to the public catalog pages plus the web-only
 * slots. Invite-only FX Hub paths are not public routes.
 * lib/legacy-dashboard.test.ts pins that.
 */

export const LEGACY_DESK_PATHS = [
  "/brief",
  "/portfolio",
  "/portfolio/holdings",
  "/portfolio/attribution",
  "/portfolio/ledger",
  "/portfolio/theses",
  "/portfolio/tearsheet",
  "/performance",
  "/pipeline",
  "/strategies",
  "/strategies/detail",
  "/strategies/deploy",
  "/tools/terminal",
  "/tools/charts",
  "/tools/chat",
];

/** Retired apps/dashboard pages with no desk twin. They go to /app. */
export const RETIRED_DASHBOARD_PATHS = [
  "/architecture",
  "/house",
  "/library",
  "/observability",
  "/portfolio/performance",
  "/portfolio/period",
  "/portfolio/tickers",
  "/research",
  "/research/vela-spike",
  "/strategy",
  "/system",
  "/twelve-x",
  "/why",
];

/** Still served from apps/dashboard. Never redirected. */
export const DASHBOARD_ACCOUNT_PATHS = [
  "/login",
  "/signup",
  "/auth/callback",
  "/settings",
  "/settings/brokers/callback",
];

/** Live desk URL for one catalog or web-slot path. Matches deskHref. */
export function legacyDeskHref(path) {
  return `/app${path}/`;
}

/**
 * @param {string} pathname
 * @returns {string | null} destination, or null when the path is not redirected
 *   (another site, an account page, or anything unlisted)
 */
export function legacyDashboardTarget(pathname) {
  const path = pathname.split("?")[0]?.split("#")[0] ?? "";
  if (path !== "/dashboard" && !path.startsWith("/dashboard/")) return null;
  const rest = path.slice("/dashboard".length).replace(/\/+$/, "");
  if (rest === "") return "/app";
  if (LEGACY_DESK_PATHS.includes(rest)) return legacyDeskHref(rest);
  if (RETIRED_DASHBOARD_PATHS.includes(rest)) return "/app";
  return null;
}

function deskPathsLongestFirst() {
  return [...LEGACY_DESK_PATHS].sort((a, b) => b.length - a.length || a.localeCompare(b));
}

function retiredLongestFirst() {
  return [...RETIRED_DASHBOARD_PATHS].sort((a, b) => b.length - a.length || a.localeCompare(b));
}

function accountPathsLongestFirst() {
  return [...DASHBOARD_ACCOUNT_PATHS].sort((a, b) => b.length - a.length || a.localeCompare(b));
}

/** Next.js redirects(). Specific desk paths, then retired pages, then the root. */
export function legacyDashboardRedirects() {
  /** @type {{ source: string, destination: string, permanent: true }[]} */
  const rules = [];
  for (const path of deskPathsLongestFirst()) {
    const destination = legacyDeskHref(path);
    rules.push({ source: `/dashboard${path}`, destination, permanent: true });
    rules.push({ source: `/dashboard${path}/`, destination, permanent: true });
  }
  for (const path of retiredLongestFirst()) {
    rules.push({ source: `/dashboard${path}`, destination: "/app", permanent: true });
    rules.push({ source: `/dashboard${path}/`, destination: "/app", permanent: true });
  }
  rules.push({ source: "/dashboard", destination: "/app", permanent: true });
  rules.push({ source: "/dashboard/", destination: "/app", permanent: true });
  return rules;
}

/** Cloudflare Pages `_redirects` lines. No splat; see the header comment. */
export function legacyDashboardCloudflareLines() {
  /** @type {string[]} */
  const lines = [];
  for (const path of deskPathsLongestFirst()) {
    const destination = legacyDeskHref(path);
    lines.push(`/dashboard${path} ${destination} 308`);
    lines.push(`/dashboard${path}/ ${destination} 308`);
  }
  for (const path of retiredLongestFirst()) {
    lines.push(`/dashboard${path} /app 308`);
    lines.push(`/dashboard${path}/ /app 308`);
  }
  lines.push("/dashboard /app 308");
  lines.push("/dashboard/ /app 308");
  return lines;
}

/**
 * Retired static digiquant.io URLs under /olympus. Previously these bounced
 * through /dashboard (itself redirected to /app), a 2-3 hop chain once the
 * root's own trailing-slash redirect is counted. Each line here points
 * straight at the final destination in one hop. Account pages still live
 * under /dashboard (never /olympus), so they keep going there, where
 * apps/dashboard serves them with no further redirect. The trailing splat
 * only catches paths no longer in any list above; it is safe here (unlike
 * the /dashboard block) because /olympus never served account pages for it
 * to shadow.
 */
export function legacyOlympusCloudflareLines() {
  /** @type {string[]} */
  const lines = [];
  for (const path of deskPathsLongestFirst()) {
    const destination = legacyDeskHref(path);
    lines.push(`/olympus${path} ${destination} 308`);
    lines.push(`/olympus${path}/ ${destination} 308`);
  }
  for (const path of retiredLongestFirst()) {
    lines.push(`/olympus${path} /app/ 308`);
    lines.push(`/olympus${path}/ /app/ 308`);
  }
  for (const path of accountPathsLongestFirst()) {
    lines.push(`/olympus${path} /dashboard${path} 308`);
    lines.push(`/olympus${path}/ /dashboard${path} 308`);
  }
  lines.push("/olympus /app/ 308");
  lines.push("/olympus/ /app/ 308");
  lines.push("/olympus/* /app/ 308");
  return lines;
}
