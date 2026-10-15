import { legacyDashboardRedirects } from "./lib/legacy-dashboard.mjs";

/** Dev `/official-api` rewrite. Unset stays the local dashboard API on 8788. */
const DEFAULT_OFFICIAL_API_ORIGIN = "http://127.0.0.1:8788";

function officialApiRewriteOrigin() {
  const configured = (process.env.DIGIQUANT_WEB_OFFICIAL_API_ORIGIN ?? "")
    .trim()
    .replace(/\/+$/, "");
  return configured.length > 0 ? configured : DEFAULT_OFFICIAL_API_ORIGIN;
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  transpilePackages: ["@digithings/ui"],
  eslint: { ignoreDuringBuilds: true },
  // Dev preview is often opened at 127.0.0.1 while `next dev` advertises localhost.
  // Next.js 16 blocks cross-origin HMR (and client hydration) unless allowlisted.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // Dev-only same-origin proxy. Static export ignores rewrites.
  // /official-api → the dashboard API. Production calls NEXT_PUBLIC_DASHBOARD_API_URL.
  // DIGIQUANT_WEB_OFFICIAL_API_ORIGIN overrides the rewrite host. Unset stays
  // http://127.0.0.1:8788. /app is this site's terminal (the OpenTUI desk pages).
  // It is not a proxy. /dashboard is not proxied. redirects() sends it to the desk.
  // Static export ignores that function; public/_redirects carries the same map on Pages.
  async rewrites() {
    return [
      { source: "/official-api/:path*", destination: `${officialApiRewriteOrigin()}/:path*` },
    ];
  },
  async redirects() {
    return legacyDashboardRedirects();
  },
};

export default nextConfig;
