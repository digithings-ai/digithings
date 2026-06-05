import type { NextConfig } from "next";
import {
  DIGICHAT_APP_SECURITY_HEADERS,
  DIGICHAT_EMBED_SECURITY_HEADERS,
} from "./src/lib/security-headers";

const nextConfig: NextConfig = {
  output: "standalone",
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
