import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { DEFAULT_CLIENT_CONFIG } from "./deploy-config";
import { HOUSE_BACKEND_ID } from "./provider-label";
import { toStockChatPrefsConfig } from "./route-client-config";

const here = dirname(fileURLToPath(import.meta.url));
const appSrc = join(here, "..");

/**
 * The source with its comments removed.
 *
 * A pin that reads a comment reads nothing: a comment can carry the marker
 * (the pin would read the prose while the wiring says something else) and a
 * word in prose can stand in for the wiring (the pin would pass on code that
 * no longer names the backend). The comments become spaces, so the code keeps
 * its place.
 */
function codeOnly(source: string): string {
  let out = "";
  let i = 0;
  let quote: string | null = null;
  while (i < source.length) {
    const ch = source.charAt(i);
    const next = source.charAt(i + 1);
    if (quote !== null) {
      out += ch;
      if (ch === "\\" && i + 1 < source.length) {
        out += next;
        i += 2;
        continue;
      }
      if (ch === quote) quote = null;
      i += 1;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      quote = ch;
      out += ch;
      i += 1;
      continue;
    }
    if (ch === "/" && next === "/") {
      while (i < source.length && source.charAt(i) !== "\n") {
        out += " ";
        i += 1;
      }
      continue;
    }
    if (ch === "/" && next === "*") {
      while (
        i < source.length &&
        !(source.charAt(i) === "*" && source.charAt(i + 1) === "/")
      ) {
        out += source.charAt(i) === "\n" ? "\n" : " ";
        i += 1;
      }
      out += "  ";
      i += 2;
      continue;
    }
    out += ch;
    i += 1;
  }
  return out;
}

/** The one import the house backend id may come from. */
const houseBackendImport =
  /import\s*\{[^}]*\bHOUSE_BACKEND_ID\b[^}]*\}\s*from\s*["'](?:@\/lib\/|\.{1,2}\/)*provider-label["']/g;

/**
 * The static surfaces that render the chip without a session of their own:
 * the home, the baseline and the devkit. They carry no BYOK state, so they
 * name the house backend - through the shared helper, never through a copy
 * of today's value.
 */
const staticSurfaces = [
  "app/(digichat)/home-stock-client.tsx",
  "app/(baseline)/baseline/baseline-client.tsx",
  "app/(devkit)/devkit/devkit-preview.tsx",
];

/**
 * The two places in the app that may name a provider label: the embed
 * surface, which names the backend that serves its own chat, and the shared
 * helper, which names the house backend for the surfaces that have no
 * session of their own.
 */
const labelHomes = [
  "app/(digichat)/embed/embed-client.tsx",
  "lib/route-client-config.ts",
];

/** Every app source file, test files excluded. */
function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    if (!/\.tsx?$/.test(entry.name)) return [];
    if (/\.test\.tsx?$/.test(entry.name)) return [];
    return [full];
  });
}

/** The composer provider menu, the third consumer of the constant. */
const providerMenu = "components/stock/embed-composer-menu.tsx";

describe("the static composer provider chip", () => {
  it("derives the label from the shared house-backend constant, not from a literal", () => {
    const code = codeOnly(
      readFileSync(join(here, "route-client-config.ts"), "utf8"),
    );
    // One wiring for the static surfaces, and it names the constant.
    const sites = [...code.matchAll(/providerLabel\s*[:=]/g)];
    expect(sites).toHaveLength(1);
    expect(code).toMatch(/providerLabel\s*:\s*HOUSE_BACKEND_ID\b/);
    // The constant is named twice: in the import and in the wiring. A copy
    // of it - declared, destructured or shadowed - would name it a third
    // time, and a second write of the label would name it a fourth.
    expect((code.match(/\bHOUSE_BACKEND_ID\b/g) ?? []).length).toBe(2);
    expect(code.match(houseBackendImport)).toHaveLength(1);
  });

  it("leaves the static surfaces without a label of their own", () => {
    for (const surface of staticSurfaces) {
      const code = codeOnly(readFileSync(join(appSrc, surface), "utf8"));
      // A surface names no backend of its own, in any form: a property, an
      // assignment, a spread that carries one.
      expect((code.match(/providerLabel/g) ?? []).length).toBe(0);
      // And it still reads the label from the one home.
      expect(code).toMatch(/from\s*["'][^"']*route-client-config["']/);
    }
  });

  it("keeps the provider label in its two homes", () => {
    // The label is named in exactly two places in the app: the embed
    // surface, which names the backend that serves its own chat, and the
    // shared helper, which names the house backend for the surfaces that
    // have no session of their own. A third place is a copy of the naming,
    // wherever it is written - a property, an assignment, a computed key.
    const naming = sourceFiles(appSrc)
      .filter((file) => codeOnly(readFileSync(file, "utf8")).includes("providerLabel"))
      .map((file) => relative(appSrc, file))
      .sort();
    expect(naming).toEqual([...labelHomes].sort());
  });

  it("names the house backend on the static surfaces", () => {
    expect(toStockChatPrefsConfig(DEFAULT_CLIENT_CONFIG).providerLabel).toBe(
      HOUSE_BACKEND_ID,
    );
  });
});

/**
 * The house backend id has one home: `src/lib/provider-label.ts`.
 *
 * The composer provider menu lists the house backend as one provider choice
 * among the own-key ones. It used to write the id inline, twice - as the row
 * id and as the row label - while the chip read it from the constant, so the
 * two named the same backend from two places of their own and could drift
 * apart (DIG-4887).
 *
 * The behaviour test cannot see a private copy come back: a copy that
 * carries today's id renders today's id. The picker test pins the rendered
 * text, so a change of the value fails loudly - but it cannot tell a copy
 * from the constant, because both render the same thing. So the source is
 * pinned here instead, the way the provider label is pinned above.
 */
describe("the composer provider menu", () => {
  it("reads the house backend id from the shared constant, not from a literal", () => {
    const code = codeOnly(readFileSync(join(appSrc, providerMenu), "utf8"));
    // The row id and the row label both come from the constant. A copy of
    // the id - written inline, declared or shadowed - would name the literal
    // instead.
    expect(code).toMatch(/id:\s*HOUSE_BACKEND_ID\b/);
    expect(code).toMatch(/label:\s*slashName\(HOUSE_BACKEND_ID\)/);
    expect(code).not.toMatch(/["']cheaperinference["']/);
  });

  it("reads the house backend id from its one home", () => {
    const code = codeOnly(readFileSync(join(appSrc, providerMenu), "utf8"));
    // The constant is named three times: in the import, in the row id and
    // in the row label. A copy of it - declared, destructured or shadowed -
    // would name it a fourth time.
    expect((code.match(/\bHOUSE_BACKEND_ID\b/g) ?? []).length).toBe(3);
    expect(code.match(houseBackendImport)).toHaveLength(1);
  });

  it("keeps the house backend id in its one home", () => {
    // The id itself is written in one place: the module that defines it.
    // Every other app module reads it from there. The rule keys on the
    // quoted value, so a module that merely mentions the id in prose - or
    // in a longer string such as a base URL - is not a copy of it.
    const quoted = new RegExp(`["']${HOUSE_BACKEND_ID}["']`);
    const copies = sourceFiles(appSrc)
      .filter((file) => codeOnly(readFileSync(file, "utf8")).match(quoted))
      .map((file) => relative(appSrc, file))
      .sort();
    expect(copies).toEqual(["lib/provider-label.ts"]);
  });
});
