// Fails fast, with instructions, when this app's own dependencies are missing.
//
// Without it, `npm run typecheck` stops at
//   TS2688: Cannot find type definition file for '@cloudflare/workers-types'
// before typechecking a single line. That reads like a broken change, and the
// two obvious reactions to it are both wrong: editing tsconfig.json, or
// rewriting the change to make the error go away.
//
// Why the situation is confusing: apps/digithings-cron is an npm workspace
// member, so npm hoists what it can to the repository root and leaves the rest
// in the app's own node_modules — and where any given package lands depends on
// version conflicts across the whole monorepo. `vitest` can therefore resolve
// from the root while `@cloudflare/workers-types` does not, so `npm test` passes
// on a worktree where `npm run typecheck` cannot start. That is correct npm
// behaviour, not a broken install, and it is why a green test run is not evidence
// that this app is installed.

import { existsSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const TYPES_PACKAGE = "@cloudflare/workers-types";

const appDir = dirname(dirname(fileURLToPath(import.meta.url)));

// Walk up from the app looking for `node_modules/<types package>` the way
// TypeScript resolves a `types` entry. Checking only
// `apps/digithings-cron/node_modules` would miss a hoisted install and report a
// healthy worktree as broken; resolving the bare specifier would miss a
// types-only package that declares no runtime entry point.
function findTypesPackage(startDir) {
  const relativeParts = TYPES_PACKAGE.split("/");
  let dir = startDir;
  for (;;) {
    const candidate = join(dir, "node_modules", ...relativeParts);
    if (existsSync(join(candidate, "package.json"))) return candidate;
    const parent = dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

// If TypeScript can find the type library, typecheck can start and there is
// nothing to report.
if (findTypesPackage(appDir) !== null) {
  process.exit(0);
}

function findRepoRoot(startDir) {
  let dir = startDir;
  for (;;) {
    const manifest = join(dir, "package.json");
    if (existsSync(manifest)) {
      try {
        const parsed = JSON.parse(readFileSync(manifest, "utf8"));
        if (Array.isArray(parsed.workspaces)) return dir;
      } catch {
        // Unreadable or malformed manifest: keep walking up.
      }
    }
    const parent = dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

const repoRoot = findRepoRoot(appDir);
const appPath = repoRoot === null ? appDir : relative(repoRoot, appDir);
const installCommand = `cd ${appPath} && npm install --no-save --no-package-lock`;

console.error(
  [
    "digithings-cron: this app's dependencies are not installed.",
    "",
    `Cannot find '${TYPES_PACKAGE}' from ${appPath}, so \`npm run typecheck\` stops at TS2688`,
    `(Cannot find type definition file for '${TYPES_PACKAGE}') before it typechecks any source.`,
    "",
    "Nothing is wrong with your change, the pinned tests or the base branch. This is a missing",
    "install, not a broken one.",
    "",
    `Why a passing \`npm test\` does not rule this out: ${appPath} is an npm workspace member, so npm`,
    "hoists what it can to the repository root and leaves the rest in the app's own",
    `node_modules — where each package lands depends on version conflicts across the whole`,
    `monorepo, so \`vitest\` can resolve while '${TYPES_PACKAGE}' does not.`,
    "",
    "Run this from the repository root:",
    "",
    `  ${installCommand}`,
    "",
    "Then re-run `npm run typecheck`.",
  ].join("\n"),
);

process.exit(1);
