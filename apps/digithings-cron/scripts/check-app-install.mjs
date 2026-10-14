// Fails fast, with instructions, when this app's own dependencies are missing.
//
// Without it, `npm run typecheck` stops at
//   TS2688: Cannot find type definition file for '@cloudflare/workers-types'
// before typechecking a single line. That reads like a broken change, and the
// two obvious reactions to it are both wrong: editing tsconfig.json, or
// rewriting the change to make the error go away.
//
// Why this app is worth its own guard rather than a shared one: it is an npm
// workspace member, so npm hoists its dependencies toward the repository root,
// and which of the two directories a given package lands in depends on version
// conflicts across the whole monorepo. `@cloudflare/workers-types` is normally
// found in one of them rather than next to the manifest that declares it, so
// whether `tsc` can start at all is a property of the install, not of the code.

import { existsSync, readFileSync } from "node:fs";
import { dirname, join, relative, sep } from "node:path";
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

// If TypeScript can find the type library anywhere up the chain, typecheck
// starts. That is all this checks: it is an existence check, so it cannot see
// which copy resolved, or whether it is the range the app declares.
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
// Normalised to `/` so the printed command is copy-pasteable on every platform;
// `path.relative` emits `\` on win32, which cmd.exe does not accept.
const appPath = repoRoot === null ? appDir : relative(repoRoot, appDir).split(sep).join("/");
const installCommand = `cd ${appPath} && npm install --no-save --no-package-lock`;

// This describes the workspace layout, so it only makes sense when the app is
// still inside the repository. Copied out on its own `repoRoot` is null, and the
// message must not describe a workspace root that is not there. Note what it
// deliberately does not claim: which directory the package normally lands in,
// or at what version. That varies with the install, so stating it here would be
// a guess dressed as an explanation.
const layoutNote =
  repoRoot === null
    ? []
    : [
        "",
        `${appPath} is an npm workspace member, so npm hoists its dependencies toward the`,
        "repository root and this package is normally found in one of those two directories",
        "rather than beside the manifest that declares it. With it in neither, `npm test`",
        "cannot run either — this guard exists to turn a cryptic stop into a sentence, not",
        "because a green test run would be misleading.",
      ];

console.error(
  [
    "digithings-cron: this app's dependencies are not installed.",
    "",
    `Cannot find '${TYPES_PACKAGE}' from ${appPath}, so \`npm run typecheck\` stops at TS2688`,
    `(Cannot find type definition file for '${TYPES_PACKAGE}') before it typechecks any source.`,
    "",
    "The type library is missing from the whole directory chain — the app's own",
    "`node_modules` and every directory above it — so the compiler stops before it reads your",
    "source. Nothing in your change caused this, and there is no code to change: this is a",
    "missing install, not a broken one.",
    ...layoutNote,
    "",
    repoRoot === null
      ? `Run this in ${appPath}:`
      : `Run this from the repository root (skip the \`cd\` if you are already in ${appPath}):`,
    "",
    `  ${installCommand}`,
    "",
    "This writes no lockfile and leaves package.json alone.",
    "",
    "Then re-run `npm run typecheck`.",
  ].join("\n"),
);

process.exit(1);
