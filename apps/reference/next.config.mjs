import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// Repo root — the narrowest dir that holds both apps/reference and the
// shared packages (@digithings/ui, @digithings/design) it transpiles.
const monorepoRoot = join(here, "..", "..");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  transpilePackages: ["@digithings/ui", "@digithings/design"],
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
