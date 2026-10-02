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
  // Dev-only same-origin proxies. Static export ignores rewrites.
  // /official-api → the dashboard API. Production calls NEXT_PUBLIC_DASHBOARD_API_URL.
  // /dashboard → the dashboard app (basePath /dashboard on :4014) so the product
  // band's iframe stays on this origin and the walkthrough can click its sidebar.
  async rewrites() {
    return [
      { source: "/official-api/:path*", destination: "http://127.0.0.1:8788/:path*" },
      { source: "/dashboard", destination: "http://127.0.0.1:4014/dashboard/" },
      { source: "/dashboard/:path*", destination: "http://127.0.0.1:4014/dashboard/:path*" },
    ];
  },
};

export default nextConfig;
