import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// Repo root — the narrowest dir that holds both apps/reference and the
// shared packages (@digithings/ui, @digithings/design) it transpiles.
const monorepoRoot = join(here, "..", "..");
const isDev = process.env.NODE_ENV === "development";

/** URLs retired by the canon IA consolidation (#4306). `output: "export"`
 *  cannot emit redirects, and these only exist so an old link does not 404
 *  mid-session while working in `next dev` — so they are dev-only. */
async function redirects() {
  return [
    { source: "/ui", destination: "/controls", permanent: false },
    { source: "/tearsheet", destination: "/finance", permanent: false },
  ];
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  transpilePackages: ["@digithings/ui", "@digithings/design"],
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  ...(isDev ? { redirects } : {}),
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
