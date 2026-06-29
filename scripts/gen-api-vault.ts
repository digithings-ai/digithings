/**
 * Generate DigiVault notes for the API reference.
 *
 * Reads the same authored content + serializers that drive the /docs page
 * (single source of truth) and writes one Obsidian-style markdown note per
 * module and per guide into `docs/vision/api/`. The existing production sync
 * (`scripts/sync_architecture_vault.py`, triggered on push to main when
 * `docs/vision/**` changes) then upserts them into Supabase `architecture_notes`,
 * so the digithings.ai chat can search and cite the API docs.
 *
 * Run from the repo root:  node_modules/.bin/tsx scripts/gen-api-vault.ts
 * (Re-run whenever apiDocs.ts / sharedDocs.ts change; commit the output.)
 */
import { mkdirSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { modules } from "../frontend/web/src/data/modules";
import { guides } from "../frontend/digithings-web/lib/sharedDocs";
import { guideToMarkdown, moduleToMarkdown } from "../frontend/digithings-web/lib/docsSerializers";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const OUT_DIR = `${ROOT}docs/vision/api`;
const CREATED = new Date().toISOString().slice(0, 10);

/** One-line summaries for the guide notes (the curated tagline becomes FTS weight B). */
const GUIDE_SUMMARY: Record<string, string> = {
  "getting-started": "Run the digithings stack locally — prerequisites, compose, environment, and make targets.",
  authentication: "Issue and use digikey JWTs across the stack — mint a key, exchange for a token, call a service.",
  conventions: "Shared HTTP conventions across services — liveness, error envelope, correlation IDs, rate limits, CORS.",
};

function frontmatter(fields: { title: string; tags: string[]; relevance?: string[] }): string {
  const lines = [
    "---",
    `title: "${fields.title}"`,
    "type: reference",
    "status: generated",
    `created: ${CREATED}`,
    "tags:",
    ...fields.tags.map((t) => `  - ${t}`),
  ];
  if (fields.relevance?.length) {
    lines.push("relevance:", ...fields.relevance.map((r) => `  - ${r}`));
  }
  lines.push("---", "");
  return lines.join("\n");
}

function write(stem: string, body: string): string {
  const path = `${OUT_DIR}/${stem}.md`;
  writeFileSync(path, body.endsWith("\n") ? body : body + "\n", "utf8");
  return `docs/vision/api/${stem}.md`;
}

// Fresh directory each run so deletions/renames don't leave orphans behind.
if (existsSync(OUT_DIR)) rmSync(OUT_DIR, { recursive: true, force: true });
mkdirSync(OUT_DIR, { recursive: true });

const written: string[] = [];

// Guide notes
for (const g of guides) {
  const summary = GUIDE_SUMMARY[g.id] ?? g.title;
  const md = guideToMarkdown(g).replace(/^## .*\n+/, ""); // drop the leading "## Title"
  const body = `${frontmatter({ title: `${g.title} — guide`, tags: ["api", "guide"] })}# ${g.title}\n\n> ${summary}\n\n${md}\n`;
  written.push(write(`guide-${g.id}`, body));
}

// Module notes — reuse moduleToMarkdown; retitle the H1 as an API-reference note.
for (const m of modules) {
  const md = moduleToMarkdown(m).replace(`# ${m.id}\n`, `# ${m.id} — API reference\n`);
  const body = `${frontmatter({ title: `${m.id} — API reference`, tags: ["api", m.tier], relevance: [m.id] })}${md}\nSee also [[${m.id}]].\n`;
  written.push(write(`${m.id}-api`, body));
}

console.log(`Wrote ${written.length} API notes to docs/vision/api/:`);
written.forEach((p) => console.log(`  ${p}`));
