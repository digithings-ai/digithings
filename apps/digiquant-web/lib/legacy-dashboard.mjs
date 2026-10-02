/**
 * Retired operator URLs under /dashboard map onto the live desk.
 * /dashboard and /dashboard/ are the brief (/app). A known desk path uses the
 * same trailing-slash shape as deskHref. Anything else under /dashboard goes
 * to /app. The apps/dashboard package stays in the tree; it is not a destination.
 *
 * Keep LEGACY_DESK_PATHS equal to the catalog pages plus the web-only slots.
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
  "/fx",
  "/fx/ideas",
  "/fx/watch",
  "/fx/rates",
  "/fx/settings",
  "/tools/terminal",
  "/tools/charts",
  "/tools/chat",
];

/** Live desk URL for one catalog or web-slot path. Matches deskHref. */
export function legacyDeskHref(path) {
  return `/app${path}/`;
}

/**
 * @param {string} pathname
 * @returns {string | null} destination, or null when pathname is not a /dashboard URL
 */
export function legacyDashboardTarget(pathname) {
  const path = pathname.split("?")[0]?.split("#")[0] ?? "";
  if (path !== "/dashboard" && !path.startsWith("/dashboard/")) return null;
  const rest = path.slice("/dashboard".length).replace(/\/+$/, "");
  if (rest === "") return "/app";
  if (LEGACY_DESK_PATHS.includes(rest)) return legacyDeskHref(rest);
  return "/app";
}

function deskPathsLongestFirst() {
  return [...LEGACY_DESK_PATHS].sort((a, b) => b.length - a.length || a.localeCompare(b));
}

/** Next.js redirects(). Specific desk paths, then the root, then the unknown catch-all. */
export function legacyDashboardRedirects() {
  /** @type {{ source: string, destination: string, permanent: true }[]} */
  const rules = [];
  for (const path of deskPathsLongestFirst()) {
    const destination = legacyDeskHref(path);
    rules.push({ source: `/dashboard${path}`, destination, permanent: true });
    rules.push({ source: `/dashboard${path}/`, destination, permanent: true });
  }
  rules.push({ source: "/dashboard", destination: "/app", permanent: true });
  rules.push({ source: "/dashboard/", destination: "/app", permanent: true });
  rules.push({ source: "/dashboard/:path*", destination: "/app", permanent: true });
  return rules;
}

/** Cloudflare Pages `_redirects` lines. Static rules before the splat. */
export function legacyDashboardCloudflareLines() {
  /** @type {string[]} */
  const lines = [];
  for (const path of deskPathsLongestFirst()) {
    const destination = legacyDeskHref(path);
    lines.push(`/dashboard${path} ${destination} 308`);
    lines.push(`/dashboard${path}/ ${destination} 308`);
  }
  lines.push("/dashboard /app 308");
  lines.push("/dashboard/ /app 308");
  lines.push("/dashboard/* /app 308");
  return lines;
}
