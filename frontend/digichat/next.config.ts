import path from "node:path";
import type { NextConfig } from "next";
import {
  DIGICHAT_APP_SECURITY_HEADERS,
  DIGICHAT_EMBED_BAKED_SECURITY_HEADERS,
} from "./src/lib/security-headers";

const nextConfig: NextConfig = {
  output: "standalone",
  // Serve under a subpath when set (e.g. /chat for digithings.ai/chat). Unset →
  // root, so self-host (`make up-digichat`), local dev, and the legacy deploy are
  // unchanged. Must match NEXT_PUBLIC_DIGICHAT_BASE_PATH (see src/lib/base-path.ts).
  basePath: process.env.DIGICHAT_BASE_PATH || undefined,
  // When digichat shares digithings.ai with Pages (static export also uses /_next),
  // set DIGICHAT_ASSET_PREFIX=/_dtchat so CF can route digichat assets without
  // colliding with the marketing site's /_next. Unset → default root assets.
  assetPrefix: process.env.DIGICHAT_ASSET_PREFIX || undefined,
  // Pin the tracing root to the monorepo root so the standalone tree is always
  // .next/standalone/frontend/digichat/server.js — without this Next infers the
  // root from surrounding lockfiles, which breaks in git worktrees and would
  // silently move server.js out from under the Dockerfile's COPY paths (#675).
  outputFileTracingRoot: path.join(__dirname, "../.."),
  // The dev badge is fixed to a viewport corner, and /embed is routinely viewed
  // inside a ~400px popup frame where every corner is chrome — it landed on the
  // composer and hid the placeholder. Dev-only; the error overlay is unaffected.
  devIndicators: false,
  turbopack: {
    root: path.join(__dirname, "../.."),
  },
  async headers() {
    return [
      {
        // Fail-closed bake — src/proxy.ts overwrites with runtime allowlist.
        source: "/embed/:path*",
        headers: [...DIGICHAT_EMBED_BAKED_SECURITY_HEADERS],
      },
      {
        source: "/embed",
        headers: [...DIGICHAT_EMBED_BAKED_SECURITY_HEADERS],
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
