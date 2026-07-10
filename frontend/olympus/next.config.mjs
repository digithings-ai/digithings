/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  basePath: '/olympus',
  images: { unoptimized: true },
  trailingSlash: true,
  // @digithings/web ships TS source (exports "./src/index.ts") — Next must
  // transpile it, same as the sibling apps (digithings-web, digiquant-web).
  transpilePackages: ['@digithings/web'],
};

export default nextConfig;
