import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Every client-side call into the app's own API goes through `p()`
 * (src/lib/base-path.ts), which prefixes the base path the app is served
 * under (DIG-5121: /chat on digithings.ai).
 *
 * A root-absolute literal ("/api/chat") is the bug this file exists to
 * catch: it keeps working while the app is served at the root, and it breaks
 * the moment the app is served under a base path — every call 404s, because
 * the app answers under /chat/api/chat and nowhere else.
 *
 * The compatibility routes on the edge (digithings.ai/api/chat* and friends)
 * would MASK that bug: the edge still answers the unprefixed spelling. So
 * the suite has to catch it here, where nothing hides it.
 */
const appSrc = join(dirname(fileURLToPath(import.meta.url)), "..");

/**
 * Files allowed to hold a root-absolute API literal that is not a `p()` call,
 * with the reason. Anything not listed here has to use `p()`.
 */
const EXEMPT: Record<string, string> = {
  "lib/base-path.ts": "the p() helper itself; its doc comment names /api/…",
  "lib/baseline-preview.ts":
    "it checks the apex-zone upstream URL (https://digithings.ai/api/chat), not a call into the app's own API",
};

/** A root-absolute API literal, in any quote style. */
const API_LITERAL = /(["'`])(\/api\/[^"'`]*)\1/g;

/** A root-relative fetch: the shape that breaks under a base path. */
const ROOT_RELATIVE_FETCH = /fetch\(\s*["'`]\//;

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...sourceFiles(path));
      continue;
    }
    if (!/\.tsx?$/.test(entry.name)) continue;
    // Test files are not shipped and may talk about paths directly.
    if (/\.test\.tsx?$/.test(entry.name)) continue;
    out.push(path);
  }
  return out;
}

const files = sourceFiles(appSrc).map((path) => ({
  path,
  rel: relative(appSrc, path),
  source: readFileSync(path, "utf8"),
}));

describe("the app's client calls carry the base path", () => {
  it("finds the app's source files", () => {
    expect(files.length).toBeGreaterThan(20);
  });

  it("no client call fetches a root-relative path", () => {
    const offenders = files
      .filter((file) => ROOT_RELATIVE_FETCH.test(file.source))
      .map((file) => file.rel);
    expect(offenders).toEqual([]);
  });

  it("every root-absolute API literal goes through p()", () => {
    const offenders: string[] = [];
    for (const file of files) {
      if (EXEMPT[file.rel]) continue;
      for (const match of file.source.matchAll(API_LITERAL)) {
        const start = match.index ?? 0;
        const lineStart = file.source.lastIndexOf("\n", start) + 1;
        const line = file.source.slice(lineStart, file.source.indexOf("\n", start) === -1 ? undefined : file.source.indexOf("\n", start));
        const lineNumber = file.source.slice(0, start).split("\n").length;
        // Comment lines only mention paths; they do not call anything.
        const trimmed = line.trim();
        if (trimmed.startsWith("//") || trimmed.startsWith("*") || trimmed.startsWith("/*")) {
          continue;
        }
        // The literal has to be the argument of a p() call. The text right
        // before it is what says so — the call may wrap onto the next line.
        const before = file.source.slice(0, start).trimEnd();
        if (!before.endsWith("p(")) {
          offenders.push(`${file.rel}:${lineNumber} ${trimmed}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the exemptions are still the ones this file describes", () => {
    // An exemption is a hole in the net: it is only allowed while the reason
    // still holds.
    for (const [rel, reason] of Object.entries(EXEMPT)) {
      const file = files.find((candidate) => candidate.rel === rel);
      expect(file, `exempted file ${rel} is gone — drop the exemption`).toBeDefined();
      expect(reason.length).toBeGreaterThan(10);
    }
  });
});
