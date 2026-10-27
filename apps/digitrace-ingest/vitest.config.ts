import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    // Colocated `src/*.test.ts`, the same shape as the sibling Workers
    // (dashboard-api, corpus-index). tsconfig excludes them so `tsc --noEmit`
    // stays a check of the Worker program only.
    include: ["src/**/*.test.ts"],
  },
});
