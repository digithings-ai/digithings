import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
// Parent of this Next app: reference + @digithings/web + @digithings/design.
// Do not pin to the git root — that watch set OOMs the machine.
const digiwebRoot = join(here, "..");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  transpilePackages: ["@digithings/web", "@digithings/design"],
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  turbopack: {
    root: digiwebRoot,
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
