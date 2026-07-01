/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  basePath: '/olympus',
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
