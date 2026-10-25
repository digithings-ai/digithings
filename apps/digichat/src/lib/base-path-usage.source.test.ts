import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { BASE_PATH as APP_BASE_PATH, p as appP } from "./base-path";
// The shared package's own copy, by source path: the package is not
// resolvable by name from here (the workspace link is not guaranteed to point
// at this checkout), and this test is about the two copies agreeing.
// eslint-disable-next-line no-restricted-imports -- the boundary rule (DIG-3695) is about product code importing package internals; this test exists to compare the two copies in THIS checkout, so the source path is the point, not an accident.
import { BASE_PATH as UI_BASE_PATH, p as uiP } from "../../../../packages/ui/src/lib/base-path";

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
 *
 * Two roots are scanned, because the app's client code is not all in the app:
 * the shared UI package (packages/ui) renders the artifacts panel and calls
 * the app's own API from there. A root-absolute path in that package breaks
 * in exactly the same way, and a scan that only looked at apps/digichat/src
 * could not see it.
 */
const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "../../../..");
const appSrc = join(here, "..");
const uiSrc = join(repoRoot, "packages/ui/src");

const ROOTS = [
  { label: "app", dir: appSrc },
  { label: "ui", dir: uiSrc },
] as const;

/**
 * Literals allowed to stay root-absolute, one entry per LITERAL — not per
 * file.
 *
 * A file-level exemption is a hole the size of the file: the review that
 * found this rule also found a root-absolute "/api/…" sitting inside an
 * exempt file, unflagged. So an exemption names the literal it excuses, and
 * every other literal in that file is still checked.
 */
const EXEMPT: Record<string, string> = {
  "app:lib/baseline-preview.ts:/api/chat":
    "it checks the apex-zone upstream URL (https://digithings.ai/api/chat), not a call into the app's own API",
  "ui:components/chat/skins/webpage-assistant/assistant-config.ts:/api/example":
    "an example snippet for the USER's own site (the webpage-assistant skin), not a call into the digichat app",
  "ui:data/modules.ts:/chat":
    "the marketing site's own link to the digichat surface (https://digithings.ai/chat) — an apex-zone link, not a call into the app",
};

/** A root-absolute API literal, in any quote style. */
const API_LITERAL = /(["'`])(\/api\/[^"'`]*)\1/g;

/** A root-relative fetch: the shape that breaks under a base path. */
const ROOT_RELATIVE_FETCH = /fetch\(\s*["'`]\//g;

/**
 * Root-absolute literals in positions that put a URL in front of a browser
 * or a client router.
 *
 * The /api/ rule above cannot see these: a link to the app's own root route
 * ("/?mode=product") is not an API path, and it breaks under a base path
 * exactly the same way — the browser lands on the apex marketing site
 * instead of the app. That is not hypothetical: the app's root menu used
 * plain <a> links with root-absolute hrefs (route-menu.tsx), and Next's
 * <Link> is the only component that auto-prefixes basePath.
 *
 * The rule is deliberately narrow. "Any root-absolute literal" flags 134
 * places — slash commands ("/help"), GitHub API paths, module paths of the
 * marketing site — and a rule that cries wolf gets ignored. Only the
 * positions that actually produce a navigable URL are in scope.
 */
const URL_PRODUCING: ReadonlyArray<{ pattern: RegExp; group: number }> = [
  // href="/x" and href={"/x"} in JSX, src="/x" likewise.
  { pattern: /(?:href|src)\s*=\s*\{?\s*(["'`])(\/[^"'`]*)\1/g, group: 2 },
  // router.push("/x") / router.replace("/x")
  { pattern: /\.(?:push|replace)\(\s*(["'`])(\/[^"'`]*)\1/g, group: 2 },
  // location.href = "/x"
  { pattern: /location\.href\s*=\s*(["'`])(\/[^"'`]*)\1/g, group: 2 },
  // { href: "/x" } — a link built in an object literal.
  { pattern: /\bhref\s*:\s*(["'`])(\/[^"'`]*)\1/g, group: 2 },
];

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

const files = ROOTS.flatMap((root) =>
  sourceFiles(root.dir).map((path) => ({
    label: root.label,
    path,
    rel: relative(root.dir, path),
    source: readFileSync(path, "utf8"),
  })),
);

/** The exemption key for one literal in one file. */
const exemptionKey = (file: (typeof files)[number], literal: string): string =>
  `${file.label}:${file.rel}:${normaliseLiteral(literal)}`;

/**
 * A literal as it is written in the exemption list.
 *
 * A literal inside an escaped string (an example snippet inside a JSON-ish
 * string) carries the backslash with it; the exemption names the path, not
 * the escaping.
 */
const normaliseLiteral = (literal: string): string => literal.replace(/\\+$/, "");

/**
 * Every root-absolute literal that could reach the app's own API: an /api/
 * path, the argument of a root-relative fetch(), or a literal in a
 * URL-producing position.
 */
function rootAbsoluteLiterals(file: (typeof files)[number]): string[] {
  const found = new Set<string>();
  for (const match of file.source.matchAll(API_LITERAL)) {
    found.add(match[2]);
  }
  for (const match of file.source.matchAll(ROOT_RELATIVE_FETCH)) {
    // The literal that follows `fetch(` — the match starts at "fetch(".
    const literal = file.source.slice(match.index).match(/["'`](\/[^"'`]*)/)?.[1];
    if (literal) found.add(literal);
  }
  for (const { pattern, group } of URL_PRODUCING) {
    for (const match of file.source.matchAll(pattern)) {
      found.add(match[group]);
    }
  }
  return [...found];
}

describe("the app's client calls carry the base path", () => {
  it("finds the app's source files", () => {
    expect(files.length).toBeGreaterThan(20);
    // The shared package is in scope too — that is the point of it.
    expect(files.some((file) => file.label === "ui")).toBe(true);
  });

  it("no client call fetches a root-relative path", () => {
    const offenders: string[] = [];
    for (const file of files) {
      for (const match of file.source.matchAll(ROOT_RELATIVE_FETCH)) {
        const literal = file.source.slice(match.index).match(/["'`](\/[^"'`]*)/)?.[1] ?? "";
        if (!literal) continue;
        if (EXEMPT[exemptionKey(file, literal)]) continue;
        const lineNumber = file.source.slice(0, match.index).split("\n").length;
        offenders.push(`${file.label}:${file.rel}:${lineNumber} ${literal}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("every root-absolute API literal goes through p()", () => {
    const offenders: string[] = [];
    for (const file of files) {
      for (const match of file.source.matchAll(API_LITERAL)) {
        const literal = match[2];
        if (EXEMPT[exemptionKey(file, literal)]) continue;
        const start = match.index ?? 0;
        const lineStart = file.source.lastIndexOf("\n", start) + 1;
        const line = file.source.slice(
          lineStart,
          file.source.indexOf("\n", start) === -1 ? undefined : file.source.indexOf("\n", start),
        );
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
          offenders.push(`${file.label}:${file.rel}:${lineNumber} ${trimmed}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("every root-absolute URL literal goes through p()", () => {
    // A link that the browser follows to the app's own surface. Next's
    // <Link> and next/image auto-prefix basePath; a plain <a href>, an
    // object-literal href and a router.push() do not. Under /chat the
    // unprefixed form lands on the apex marketing site.
    const offenders: string[] = [];
    for (const file of files) {
      for (const { pattern, group } of URL_PRODUCING) {
        for (const match of file.source.matchAll(pattern)) {
          const literal = match[group];
          if (EXEMPT[exemptionKey(file, literal)]) continue;
          const start = match.index ?? 0;
          const lineNumber = file.source.slice(0, start).split("\n").length;
          offenders.push(`${file.label}:${file.rel}:${lineNumber} ${literal}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("the shared package reads the base path the way the framework inlines it", () => {
    // The framework inlines `process.env.NEXT_PUBLIC_*` into the bundle. A
    // `typeof process` guard reads as "process is missing" in the browser, so
    // it would swallow the inlined value and the app would serve at the root
    // — the exact failure this whole change exists to prevent. The app's own
    // copy (apps/digichat/src/lib/base-path.ts) reads it the same way.
    const shared = readFileSync(join(uiSrc, "lib/base-path.ts"), "utf8");
    expect(shared).not.toMatch(/typeof\s+process\s*(!==|===)/);
    expect(shared).toMatch(/process\.env\.NEXT_PUBLIC_DIGICHAT_BASE_PATH/);
  });

  it("the app and the shared UI package read the SAME base path", () => {
    // Two copies of the helper exist — one in the app, one in the shared
    // package — because the package cannot import the app's source. They must
    // not drift: the app answers under one prefix and the client must use the
    // same one.
    expect(UI_BASE_PATH).toBe(APP_BASE_PATH);
    expect(uiP("/api/conversations/x/artifacts")).toBe(appP("/api/conversations/x/artifacts"));
  });

  it("the exemptions are still the ones this file describes", () => {
    // An exemption is a hole in the net: it is only allowed while the reason
    // still holds, and it has to point at a literal that is really there.
    for (const [key, reason] of Object.entries(EXEMPT)) {
      const separator = key.indexOf(":/");
      const file = files.find(
        (candidate) => `${candidate.label}:${candidate.rel}` === key.slice(0, separator),
      );
      expect(file, `exempted file ${key} is gone — drop the exemption`).toBeDefined();
      expect(reason.length).toBeGreaterThan(10);
      const literal = key.slice(separator + 1);
      expect(
        rootAbsoluteLiterals(file!).map(normaliseLiteral),
        `the exempted literal ${literal} is gone — drop the exemption`,
      ).toContain(literal);
    }
  });
});
