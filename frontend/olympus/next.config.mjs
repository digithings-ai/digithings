/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  basePath: '/olympus',
  images: { unoptimized: true },
  trailingSlash: true,
  // @digithings/web ships TypeScript sources (exports "." → src/index.ts) —
  // Next must compile them (same wiring as digithings-web / digiquant-web).
  transpilePackages: ['@digithings/web'],
};

export default nextConfig;
