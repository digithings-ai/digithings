import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  test: {
    environment: "node",
    // .test.js: container-id-deploy.test.js imports the plain .mjs deploy
    // wrapper, which has no TypeScript declarations. tsconfig.json includes only
    // *.ts, so a .js test is collected here and stays out of `tsc --noEmit`
    // rather than needing a hand-written .d.ts that could itself drift.
    // Mirrors the same split in apps/digithings-stack-cloudflare.
    include: ["src/**/*.test.ts", "src/**/*.test.js"],
  },
  resolve: {
    alias: {
      // index.ts reads `env` from the Workers runtime at module scope, so a
      // unit test needs a stand-in for the module. Mirrors the same alias in
      // apps/digiquant-runner.
      "cloudflare:workers": path.resolve(root, "test/cloudflare-workers-stub.ts"),
    },
  },
});
