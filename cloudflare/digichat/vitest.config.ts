import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    setupFiles: ["./vitest.setup.ts"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      // Prefer the sibling package sources in this checkout / worktree (#3556).
      "@digithings/digichat-ui": path.resolve(__dirname, "../digichat-ui/src/index.ts"),
    },
  },
});
