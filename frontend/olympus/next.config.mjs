/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  basePath: '/olympus',
  images: { unoptimized: true },
  trailingSlash: true,
  // @digithings/web ships raw TS sources (exports "." → src/index.ts) —
  // Next must transpile it (same wiring as digithings-web).
  transpilePackages: ['@digithings/web'],
};

export default nextConfig;
