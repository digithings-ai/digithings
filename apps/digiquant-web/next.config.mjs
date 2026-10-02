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
  // Dev-only same-origin proxy. Static export ignores rewrites.
  // /official-api → the dashboard API. Production calls NEXT_PUBLIC_DASHBOARD_API_URL.
  // /app is this site's terminal (the OpenTUI desk pages). It is not a proxy.
  // /dashboard is not proxied. That path used to be the brief desk.
  async rewrites() {
    return [{ source: "/official-api/:path*", destination: "http://127.0.0.1:8788/:path*" }];
  },
};

export default nextConfig;
