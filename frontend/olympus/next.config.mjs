/** @type {import('next').NextConfig} */
const olympusBasePath = '/olympus';

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
  // Dev preview is often opened at 127.0.0.1 while `next dev` advertises localhost.
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
};

export default nextConfig;
