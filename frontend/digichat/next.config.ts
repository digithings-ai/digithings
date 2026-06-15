import path from "node:path";
import type { NextConfig } from "next";
import {
  DIGICHAT_APP_SECURITY_HEADERS,
  DIGICHAT_EMBED_SECURITY_HEADERS,
} from "./src/lib/security-headers";

const nextConfig: NextConfig = {
  output: "standalone",
  // Serve under a subpath when set (e.g. /chat for digithings.ai/chat). Unset →
  // root, so self-host (`make up-digichat`), local dev, and the legacy deploy are
  // unchanged. Must match NEXT_PUBLIC_DIGICHAT_BASE_PATH (see src/lib/base-path.ts).
  basePath: process.env.DIGICHAT_BASE_PATH || undefined,
  // Pin the tracing root to the monorepo root so the standalone tree is always
  // .next/standalone/frontend/digichat/server.js — without this Next infers the
  // root from surrounding lockfiles, which breaks in git worktrees and would
  // silently move server.js out from under the Dockerfile's COPY paths (#675).
  outputFileTracingRoot: path.join(__dirname, "../.."),
  turbopack: {
    root: path.join(__dirname, "../.."),
  },
  async headers() {
    return [
      {
        source: "/embed/:path*",
        headers: [...DIGICHAT_EMBED_SECURITY_HEADERS],
      },
      {
        source: "/embed",
        headers: [...DIGICHAT_EMBED_SECURITY_HEADERS],
      },
      {
        // All non-embed routes — global CSP + hardening (REM-077).
        source: "/((?!embed$|embed/).*)",
        headers: [...DIGICHAT_APP_SECURITY_HEADERS],
      },
    ];
  },
};

export default nextConfig;
