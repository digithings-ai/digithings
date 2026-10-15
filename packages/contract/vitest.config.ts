import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// performance-ssot imports `@digithings/ui`. Alias it to the dependency-free
// KPI module — the package index pulls React.
const uiKpis = fileURLToPath(
  new URL(
    "../ui/src/components/finance-tearsheet/live-performance-kpis.ts",
    import.meta.url,
  ),
);

export default defineConfig({
  resolve: {
    alias: {
      "@digithings/ui": uiKpis,
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
