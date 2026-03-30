#!/usr/bin/env node
/**
 * After `vite build` (outDir dist/), copy publishable files next to package.json
 * so GitHub Pages can serve website/digichat/ at /digichat/ without committing dist/.
 *
 * Only index.html + assets/ (not loose public/ copies) so logos stay via bundled imports + public/ for dev.
 */
import { cpSync, existsSync, rmSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const dist = join(root, "dist");

if (!existsSync(dist)) {
  console.error("dist/ missing — run: npm run build");
  process.exit(1);
}

cpSync(join(dist, "index.html"), join(root, "index.html"));

const assetsOut = join(root, "assets");
if (existsSync(assetsOut)) {
  rmSync(assetsOut, { recursive: true });
}
cpSync(join(dist, "assets"), assetsOut, { recursive: true });

console.log("Synced dist/ → website/digichat/ (index.html, assets/)");
