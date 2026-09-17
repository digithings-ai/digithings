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
      // "@digithings/web" entry below would otherwise swallow
      // "@digithings/web/ui" and resolve it as `src/index.ts/ui`.
      "@digithings/web/ui": path.resolve(__dirname, "../digiweb/web/src/ui/index.ts"),
      "@digithings/web": path.resolve(__dirname, "../digiweb/web/src/index.ts"),
    },
  },
});
