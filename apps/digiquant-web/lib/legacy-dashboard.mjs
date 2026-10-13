/**
 * Retired operator URLs under /dashboard map onto the live desk at /app.
 * A known desk path uses the same trailing-slash shape as deskHref. Retired
 * dashboard pages with no desk twin go to /app. There is no catch-all: the
 * account pages (login, signup, Auth callback, settings, Alpaca OAuth
 * callback) and FX Hub still ship from apps/dashboard under /dashboard.
 * Account pages are pinned by Supabase Edge Functions (app-url.ts), Stripe
 * returns and scripts/build-digiquant.sh. A splat would shadow them.
 *
 * This release keeps FX Hub on apps/dashboard (DIG-3315). Invite links are
 * https://digiquant.io/dashboard?invite=<code> (apps/dashboard/AUTH.md), so
 * /dashboard and /dashboard/ are not redirected. /dashboard/twelve-x is the
 * FX Hub page and stays there too. Non-FX desk paths still 308 to /app.
 *
 * Later, when the FX Hub inside /app is the one clients should use, set
 * ROUTE_DASHBOARD_FX_HUB_TO_APP to true. That sends the root and
 * DASHBOARD_FX_HUB_PATHS to /app. Do not flip it in this release.
 *
 * Keep LEGACY_DESK_PATHS equal to the public catalog pages plus the web-only
 * slots. The desk /settings pages are left out: /dashboard/settings is still
 * the account page. lib/legacy-dashboard.test.ts pins that.
 */

/** Flip only after the new FX Hub inside /app replaces this dashboard page. */
export const ROUTE_DASHBOARD_FX_HUB_TO_APP = false;

/** FX Hub routes that stay on apps/dashboard while the flag above is false. */
export const DASHBOARD_FX_HUB_PATHS = ["/twelve-x"];

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
  // The brief IS the app: it lives at /app, never /app/brief.
  if (path === "/brief") return "/app/";
  return `/app${path}/`;
}

/**
 * @param {{ routeFxHubToApp?: boolean }} [options]
 * @returns {boolean}
 */
function routeFxHubToApp(options) {
  return options?.routeFxHubToApp ?? ROUTE_DASHBOARD_FX_HUB_TO_APP;
}

/** True for /twelve-x and anything nested under it. */
function isFxHubRest(rest) {
  return DASHBOARD_FX_HUB_PATHS.some((path) => rest === path || rest.startsWith(`${path}/`));
}

/**
 * @param {string} pathname
 * @param {{ routeFxHubToApp?: boolean }} [options]
 * @returns {string | null} destination, or null when the path is not redirected
 *   (another site, an account page, FX Hub while it stays on the dashboard,
 *   or anything unlisted)
 */
export function legacyDashboardTarget(pathname, options) {
  const path = pathname.split("?")[0]?.split("#")[0] ?? "";
  if (path !== "/dashboard" && !path.startsWith("/dashboard/")) return null;
  const rest = path.slice("/dashboard".length).replace(/\/+$/, "");
  if (rest === "" || isFxHubRest(rest)) {
    return routeFxHubToApp(options) ? "/app" : null;
  }
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

function fxHubPathsLongestFirst() {
  return [...DASHBOARD_FX_HUB_PATHS].sort((a, b) => b.length - a.length || a.localeCompare(b));
}

/**
 * Root and FX Hub rules. Empty while FX Hub stays on apps/dashboard.
 * @param {{ routeFxHubToApp?: boolean }} [options]
 */
function fxHubDashboardRules(options) {
  if (!routeFxHubToApp(options)) return [];
  /** @type {{ source: string, destination: string, permanent: true }[]} */
  const rules = [];
  for (const path of fxHubPathsLongestFirst()) {
    rules.push({ source: `/dashboard${path}`, destination: "/app", permanent: true });
    rules.push({ source: `/dashboard${path}/`, destination: "/app", permanent: true });
  }
  rules.push({ source: "/dashboard", destination: "/app", permanent: true });
  rules.push({ source: "/dashboard/", destination: "/app", permanent: true });
  return rules;
}

/** Next.js redirects(). Specific desk paths, then retired pages. FX Hub last, and only when the flag is on. */
export function legacyDashboardRedirects(options) {
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
  rules.push({ source: "/app/brief", destination: "/app/", permanent: true });
  rules.push({ source: "/app/brief/", destination: "/app/", permanent: true });
  rules.push(...fxHubDashboardRules(options));
  return rules;
}

/** Cloudflare Pages `_redirects` lines. No splat on /dashboard; see the header comment. */
export function legacyDashboardCloudflareLines(options) {
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
  for (const rule of fxHubDashboardRules(options)) {
    lines.push(`${rule.source} ${rule.destination} 308`);
  }
  return lines;
}

/**
 * Retired static digiquant.io URLs under /olympus. Previously these bounced
 * through /dashboard (itself redirected to /app), a 2-3 hop chain once the
 * root's own trailing-slash redirect is counted. Each line here points
 * straight at the final destination in one hop. Account pages and FX Hub
 * still live under /dashboard (never /olympus), so they keep going there,
 * where apps/dashboard serves them with no further redirect. The trailing
 * splat only catches paths no longer in any list above; it is safe here
 * (unlike the /dashboard block) because /olympus never served account pages
 * for it to shadow. FX Hub rules sit before that splat.
 */
export function legacyOlympusCloudflareLines(options) {
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
  if (routeFxHubToApp(options)) {
    for (const path of fxHubPathsLongestFirst()) {
      lines.push(`/olympus${path} /app/ 308`);
      lines.push(`/olympus${path}/ /app/ 308`);
    }
  } else {
    for (const path of fxHubPathsLongestFirst()) {
      lines.push(`/olympus${path} /dashboard${path} 308`);
      lines.push(`/olympus${path}/ /dashboard${path}/ 308`);
      lines.push(`/olympus${path}/* /dashboard${path}/:splat 308`);
    }
  }
  lines.push("/olympus /app/ 308");
  lines.push("/olympus/ /app/ 308");
  lines.push("/olympus/* /app/ 308");
  return lines;
}
