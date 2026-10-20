import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["components/**/*.test.ts", "components/**/*.test.tsx", "lib/**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
      // Subpath first: Vite alias matching is prefix-based, so the bare
      // "@digithings/ui" entry below would otherwise swallow
      // "@digithings/ui/ui" and resolve it as `src/index.ts/ui`.
      "@digithings/ui/ui": path.resolve(__dirname, "../../packages/ui/src/ui/index.ts"),
      "@digithings/ui": path.resolve(__dirname, "../../packages/ui/src/index.ts"),
    },
  },
});
