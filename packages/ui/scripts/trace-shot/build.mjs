// Build the trace screenshot harness: DigichatThread with a fixed trace
// (reasoning + two tool calls + answer) and the real chat stylesheets.
//   node packages/ui/scripts/trace-shot/build.mjs
// Writes out/trace.js and out/trace.css next to this file (gitignored).
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import tailwind from "@tailwindcss/postcss";
import { build } from "esbuild";
import postcss from "postcss";

const here = (p) => new URL(p, import.meta.url).pathname;
mkdirSync(here("./out"), { recursive: true });

await build({
  entryPoints: [here("./entry.tsx")],
  bundle: true,
  outfile: here("./out/trace.js"),
  format: "iife",
  jsx: "automatic",
  loader: { ".svg": "dataurl" },
  define: { "process.env.NODE_ENV": '"development"' },
  logLevel: "warning",
});

const from = here("./in.css");
const css = await postcss([tailwind()]).process(readFileSync(from, "utf8"), { from });
writeFileSync(here("./out/trace.css"), css.css);
console.log("built out/trace.js and out/trace.css");
