import { defineConfig } from "vitest/config";

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
});
