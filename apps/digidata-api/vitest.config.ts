import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Slice 0007 validation imports the REAL client derivations from
// apps/dashboard/lib/*. The only non-relative import in that closure is
// `@digithings/ui` (performance-ssot.ts uses computeLivePerformanceKpis +
// sinceInceptionPctFromNav). Alias it to the dependency-free source module
// those two functions live in — not the package index (which pulls React).
const uiKpis = fileURLToPath(
  new URL(
    "../../packages/ui/src/components/finance-tearsheet/live-performance-kpis.ts",
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
