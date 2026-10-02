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
  // Dev-only same-origin proxy so the preview can read the local official API.
  // Static export ignores rewrites; production calls NEXT_PUBLIC_DASHBOARD_API_URL.
  async rewrites() {
    return [{ source: "/official-api/:path*", destination: "http://127.0.0.1:8788/:path*" }];
  },
};

export default nextConfig;
