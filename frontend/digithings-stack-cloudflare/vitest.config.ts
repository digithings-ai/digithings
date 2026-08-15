import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    // .test.js: env-vars-pin.test.js reads node:fs/node:path/node:url, which have
    // no ambient types in this Workers-only tsconfig (see that file's docstring).
    include: ["src/**/*.test.ts", "src/**/*.test.js"],
  },
});
