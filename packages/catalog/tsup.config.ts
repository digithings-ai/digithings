import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts", "src/byok-providers.ts", "src/openapi.ts", "src/page-context-sanitize.ts"],
  format: ["esm"],
  dts: true,
  clean: true,
  treeshake: true,
});
