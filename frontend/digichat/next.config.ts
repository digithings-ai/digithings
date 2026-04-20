import type { NextConfig } from "next";

/**
 * Allowlist of origins permitted to iframe the /embed surface.
 * Keep this narrow — CSP frame-ancestors is the sole defense against
 * cross-origin framing of the unauthenticated embed.
 */
const EMBED_FRAME_ANCESTORS = [
  "'self'",
  "https://digithings.ai",
  "https://digiquant.io",
].join(" ");

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    return [
      {
        // Only the embed route gets frame-ancestors relaxation + nosniff.
        // The authenticated app chrome remains default-deny via standard
        // Next.js headers / hosting config.
        source: "/embed/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: `frame-ancestors ${EMBED_FRAME_ANCESTORS};`,
          },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
      {
        source: "/embed",
        headers: [
          {
            key: "Content-Security-Policy",
            value: `frame-ancestors ${EMBED_FRAME_ANCESTORS};`,
          },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
    ];
  },
};

export default nextConfig;
