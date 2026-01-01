import path from "node:path";
import { defineConfig } from "vitest/config";

/**
 * The reference canon's contract tests. Node environment, no DOM — every test
 * reads the source tree (route files, specimen files, nav data, family CSS)
 * and pins the structure the IA consolidation promises. These are the tests
 * the canon had none of before workstream A (#4306).
 */
export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname) },
  },
});
