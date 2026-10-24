import { readFileSync } from "node:fs";

/**
 * The CLI's version, read from its package.json at run time. Both `src/` (tsx)
 * and `dist/` (built) sit one level below the package root, so one relative
 * URL serves both, and the bump in package.json is the only place to edit.
 */
export function cliVersion(): string {
  const pkg = JSON.parse(
    readFileSync(new URL("../package.json", import.meta.url), "utf8"),
  ) as { version?: unknown };
  if (typeof pkg.version !== "string" || !pkg.version) {
    throw new Error("digichat cli: package.json has no version");
  }
  return pkg.version;
}
