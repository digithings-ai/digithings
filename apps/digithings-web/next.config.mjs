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
  // Cloudflare Pages serves dist/openwiki/index.html for /openwiki/. `next dev`
  // does not directory-index public/, so the Wiki nav 404s locally without this.
  // Static export ignores rewrites (Cloudflare still serves the directory index).
  async rewrites() {
    return [
      { source: "/openwiki/", destination: "/openwiki/index.html" },
      // The market-data Worker allows digithings.ai, not a local preview.
      // Dev-only: .env.local points the band here so the benchmark leg is the
      // same series production draws. Static export ignores this rewrite.
      { source: "/market-data/:path*", destination: "https://graph.digithings.ai/:path*" },
    ];
  },
};

export default nextConfig;
