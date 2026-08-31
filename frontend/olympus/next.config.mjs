/** @type {import('next').NextConfig} */
const dashboardBasePath = '/dashboard';

const nextConfig = {
  output: 'export',
  basePath: dashboardBasePath,
  images: { unoptimized: true },
  trailingSlash: true,
  // Surface basePath to client code (static export has no runtime config).
  // Used by oauthRedirectTo() so PKCE redirect_to matches AUTH.md allow-list.
  env: {
    NEXT_PUBLIC_DASHBOARD_BASE_PATH: dashboardBasePath,
    // One-release alias — Cloudflare Pages may still inject the old name.
    NEXT_PUBLIC_OLYMPUS_BASE_PATH: dashboardBasePath,
  },
  // @digithings/web ships TypeScript sources (exports "." → src/index.ts) —
  // Next must compile them (same wiring as digithings-web / digiquant-web).
  transpilePackages: ['@digithings/web'],
  // Dev preview is often opened at 127.0.0.1 while `next dev` advertises localhost.
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
};

export default nextConfig;
