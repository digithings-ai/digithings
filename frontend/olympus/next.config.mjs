/** @type {import('next').NextConfig} */
const ALLOWED_BASE_PATHS = new Set(['/olympus', '/dashboard']);
const olympusBasePath = process.env.OLYMPUS_BASE_PATH || '/olympus';
if (!ALLOWED_BASE_PATHS.has(olympusBasePath)) {
  throw new Error(
    `OLYMPUS_BASE_PATH must be /olympus or /dashboard, got ${JSON.stringify(olympusBasePath)}`,
  );
}

const nextConfig = {
  output: 'export',
  basePath: olympusBasePath,
  images: { unoptimized: true },
  trailingSlash: true,
  // Surface basePath to client code (static export has no runtime config).
  // Used by oauthRedirectTo() so PKCE redirect_to matches AUTH.md allow-list.
  env: {
    NEXT_PUBLIC_OLYMPUS_BASE_PATH: olympusBasePath,
  },
  // @digithings/web ships TypeScript sources (exports "." → src/index.ts) —
  // Next must compile them (same wiring as digithings-web / digiquant-web).
  transpilePackages: ['@digithings/web'],
};

export default nextConfig;
