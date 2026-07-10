/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  basePath: '/olympus',
  images: { unoptimized: true },
  trailingSlash: true,
  // @digithings/web ships TS source (workspace package) — Next must compile it.
  transpilePackages: ['@digithings/web'],
};

export default nextConfig;
