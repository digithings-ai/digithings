import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  // @digithings/hero-banner ships .tsx source with no tsconfig of its own, so
  // esbuild would fall back to the classic runtime (React.createElement).
  esbuild: { jsx: "automatic" },
  test: { environment: "node" },
});
