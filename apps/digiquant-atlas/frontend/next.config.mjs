/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  basePath: '/digiquant-atlas',
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
