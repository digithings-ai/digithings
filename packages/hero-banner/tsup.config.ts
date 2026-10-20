import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts", "src/definitions/index.ts", "src/web.tsx", "src/tui.ts", "src/canvas.ts"],
  format: ["esm"],
  dts: true,
  clean: true,
  treeshake: true,
  external: ["react"],
});
