import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
  resolve: {
    // The Durable Object classes import `DurableObject` from `cloudflare:workers`,
    // which only resolves inside the Workers runtime. The stub keeps the same
    // shape, so the unit tests drive the class the way production does.
    alias: {
      "cloudflare:workers": path.resolve(root, "test/cloudflare-workers-stub.ts"),
    },
  },
});
