import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts", "src/definitions/index.ts", "src/web.tsx"],
  format: ["esm"],
  dts: true,
  clean: true,
  treeshake: true,
  external: ["react"],
});
