import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// Repo root — the narrowest dir that holds both apps/digiweb and the shared
// packages (@digithings/ui, @digithings/design, @digithings/hero-banner) it
// transpiles.
const monorepoRoot = join(here, "..", "..");

/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: { agentUpgrade: "security" },
  output: "export",
  images: { unoptimized: true },
  // One root layout now, so `app/not-found.tsx` is a page body under the
  // shared document. `output: "export"` emits out/404.html from it.
  trailingSlash: true,
  transpilePackages: ["@digithings/ui", "@digithings/design", "@digithings/hero-banner"],
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  turbopack: {
    root: monorepoRoot,
  },
  webpack: (config, { dev }) => {
    if (dev) {
      config.watchOptions = {
        ...config.watchOptions,
        followSymlinks: false,
        ignored: [
          "**/node_modules/**",
          "**/.git/**",
          "**/.next/**",
          "**/.worktrees/**",
          "**/.venv/**",
          "**/__pycache__/**",
        ],
      };
    }
    return config;
  },
};

export default nextConfig;
