#!/usr/bin/env node
/**
 * build-manifest.mjs — regenerate frontend/digiweb/MANIFEST.json.
 *
 * Walks the reference app and emits a machine-readable index of every reusable
 * component so agents can discover patterns without reading each file. Structure
 * (name, path, family) is derived from the filesystem + which family page imports
 * the component; the human summary is the component's leading /** *\/ docblock.
 *
 * Run:  node frontend/digiweb/scripts/build-manifest.mjs
 * No dependencies — plain Node ESM + regex parsing.
 */
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const DIGIWEB = dirname(dirname(fileURLToPath(import.meta.url)));
const REF = join(DIGIWEB, "reference");
const COMPONENTS = join(REF, "components");
const APP = join(REF, "app");

/** Recursively list files under `dir` matching `ext`. */
function walk(dir, ext, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      if (entry === "node_modules" || entry === ".next") continue;
      walk(full, ext, out);
    } else if (full.endsWith(ext)) {
      out.push(full);
    }
  }
  return out;
}

/** Family for each page: app/page.tsx → foundations; app/<fam>/page.tsx → <fam>. */
function pageFamily(pagePath) {
  const rel = relative(APP, pagePath);
  const dir = dirname(rel);
  return dir === "." ? "foundations" : dir.split("/")[0];
}

/** Resolve a `@/components/...` import specifier to an absolute component path. */
function resolveSpecifier(spec) {
  const sub = spec.replace(/^@\/components\//, "");
  for (const cand of [`${sub}.tsx`, `${sub}.ts`, `${sub}/index.tsx`]) {
    const full = join(COMPONENTS, cand);
    try {
      if (statSync(full).isFile()) return full;
    } catch {
      /* not this candidate */
    }
  }
  return null;
}

// 1. Map component file → family by scanning each page's component imports.
const familyByFile = new Map();
for (const page of walk(APP, "page.tsx")) {
  const fam = pageFamily(page);
  const src = readFileSync(page, "utf8");
  const importRe = /from\s+"(@\/components\/[^"]+)"/g;
  let m;
  while ((m = importRe.exec(src))) {
    const file = resolveSpecifier(m[1]);
    if (file && !familyByFile.has(file)) familyByFile.set(file, fam);
  }
}

// 2. Extract metadata for every component file.
/** First `/** … *\/` docblock, flattened to one line, first sentence kept. */
function docSummary(src) {
  const block = src.match(/\/\*\*([\s\S]*?)\*\//);
  if (!block) return null;
  const text = block[1]
    .split("\n")
    .map((l) => l.replace(/^\s*\*?\s?/, "").trim())
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return null;
  const stop = text.search(/\.\s|\. *$/);
  return (stop > 0 ? text.slice(0, stop + 1) : text).trim();
}

/**
 * Exported component/const names, PascalCase or hook-like only.
 *
 * Both declaration and re-export forms count. A component PROMOTED into
 * @digithings/web leaves a `export { X } from "@digithings/web"` behind so the
 * specimen keeps a stable import path against one implementation — and matching
 * only `export function` silently dropped all three of the first batch out of
 * the index, which is the one place an agent is told to look for them.
 */
function exportNames(src) {
  const names = new Set();
  const declRe = /export\s+(?:async\s+)?(?:function|const)\s+([A-Za-z0-9_]+)/g;
  let m;
  while ((m = declRe.exec(src))) names.add(m[1]);

  // `export { A, B as C, type D } from "…"` — value exports only; a re-exported
  // type is not a component and would otherwise index as one.
  const reexportRe = /export\s*\{([^}]*)\}\s*from\s*"[^"]+"/g;
  while ((m = reexportRe.exec(src))) {
    for (const part of m[1].split(",")) {
      const spec = part.trim();
      if (!spec || spec.startsWith("type ")) continue;
      const local = spec.split(/\s+as\s+/).pop().trim();
      if (local) names.add(local);
    }
  }
  return [...names];
}

/**
 * The entry's headline export. Declaration order alone is not enough once a
 * file mixes a promoted re-export with a local helper: product-frame.tsx
 * re-exports <ProductFrame> and declares <MockTearsheet> beside it, and taking
 * the first found renamed the entry after the helper. The filename is the
 * component's identity, so match against it and fall back to first-found.
 */
function primaryName(names, id) {
  const pascal = id.split("-").map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join("");
  return (
    names.find((n) => n === pascal) ?? names.find((n) => n.endsWith(pascal)) ?? names[0]
  );
}

/** The shared module a pure re-export stub forwards to, if that is all it is. */
function promotedTo(src) {
  if (/export\s+(?:async\s+)?(?:function|const)\s/.test(src)) return null;
  const m = src.match(/export\s*\{[^}]*\}\s*from\s*"(@digithings\/[^"]+)"/);
  return m ? m[1] : null;
}

const families = {};
let described = 0;
let total = 0;

for (const file of walk(COMPONENTS, ".tsx").sort()) {
  const src = readFileSync(file, "utf8");
  const names = exportNames(src).filter((n) => /^[A-Z]/.test(n));
  if (names.length === 0) continue; // skip pure type/util modules
  total += 1;
  const relPath = relative(DIGIWEB, file);
  const base = file.split("/").pop().replace(/\.tsx$/, "");
  const id = base.replace(/-reference$/, "");
  const subdir = relative(COMPONENTS, dirname(file));
  const family = familyByFile.get(file) || (subdir && subdir !== "." ? subdir : "shared");
  const summary = docSummary(src);
  if (summary) described += 1;
  const shared = promotedTo(src);
  (families[family] ||= []).push({
    name: primaryName(names, id),
    id,
    path: relPath,
    // Where the implementation actually lives, when `path` is only the stub
    // left behind by a promotion. Consume from here, not from the reference.
    ...(shared ? { promotedTo: shared } : {}),
    summary,
    ...(names.length > 1 ? { exports: names } : {}),
  });
}

for (const list of Object.values(families)) list.sort((a, b) => a.id.localeCompare(b.id));

const manifest = {
  generatedAt: new Date().toISOString(),
  source: relative(join(DIGIWEB, ".."), REF),
  note: "Generated by scripts/build-manifest.mjs — do not hand-edit. Run the script to refresh.",
  counts: { components: total, described, families: Object.keys(families).length },
  families: Object.fromEntries(Object.keys(families).sort().map((k) => [k, families[k]])),
};

writeFileSync(join(DIGIWEB, "MANIFEST.json"), JSON.stringify(manifest, null, 2) + "\n");
console.log(
  `MANIFEST.json: ${total} components across ${manifest.counts.families} families, ` +
    `${described} described (${Math.round((described / total) * 100)}% docblock coverage).`,
);
