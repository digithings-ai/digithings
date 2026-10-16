import { describe, expect, it } from "vitest";
import envSrc from "./env.ts?raw";
import httpSrc from "./http.ts?raw";
import supabaseAuthSrc from "./supabase-auth.ts?raw";
import sessionSrc from "./session.ts?raw";
import grantSyncSrc from "./grant-sync.ts?raw";
import routerSrc from "./router.ts?raw";
import indexSrc from "../index.ts?raw";

// Two properties the port has to hold for the cutover to be a cutover rather
// than a rewrite:
//
//   1. No Deno global survives anywhere in the tree. A single `Deno.env.get`
//      left behind would throw at request time on Workers, not at build time,
//      and the only warning would be a 500 in production.
//   2. The dashboard-api entrypoint mounts this module on FX_HUB_PATHS.
//      A comment that merely mentions fx-hub does not count: the import
//      has to be in code.
//
// Source text is read with Vite's `?raw` import because tsconfig for this
// package has no `@types/node`, so `node:fs` cannot be used here.

const SOURCES: Record<string, string> = {
  "env.ts": envSrc,
  "http.ts": httpSrc,
  "supabase-auth.ts": supabaseAuthSrc,
  "session.ts": sessionSrc,
  "grant-sync.ts": grantSyncSrc,
  "router.ts": routerSrc,
};

/** Removes block and line comments so the scans below read CODE, not prose. */
function code(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

describe("the ported fx-hub tree is Deno-free", () => {
  it("strips comments, so the scans read code and not the prose describing it", () => {
    const sample = "/** mentions Deno.env */\nconst x = 1; // and Deno.serve";
    expect(code(sample)).not.toMatch(/Deno/);
    expect(code(sample)).toContain("const x = 1;");
    expect(code(sample).trim()).toBe("const x = 1;");
  });

  it("reads back a non-trivial amount of source, so the scan is not vacuous", () => {
    const total = Object.values(SOURCES).reduce((n, src) => n + src.length, 0);
    expect(total).toBeGreaterThan(1500);
    for (const [name, src] of Object.entries(SOURCES)) {
      expect(src.length, `${name} resolved to an empty string`).toBeGreaterThan(0);
    }
  });

  it("contains no Deno global in any ported module", () => {
    for (const [name, src] of Object.entries(SOURCES)) {
      const hits = code(src).match(/\bDeno\b/g);
      expect(hits, `${name} still references Deno in code`).toBeNull();
    }
  });

  it("does not call Deno.serve or Deno.env through an indirect spelling", () => {
    const joined = Object.values(SOURCES).map(code).join("\n");
    expect(joined).not.toMatch(/Deno\s*\./);
    expect(joined).not.toMatch(/serve\s*\(\s*\(?\s*req/);
  });

  it("declares no worker binding, var or secret name in a wrangler config", () => {
    const joined = Object.values(SOURCES).map(code).join("\n");
    expect(joined).not.toMatch(/\[vars\]|\[secrets\]|\[\[kv_namespaces\]\]/);
  });
});

describe("router surface", () => {
  it("declares the two ported paths", () => {
    expect(routerSrc).toContain("/fx-hub-session");
    expect(routerSrc).toContain("/fx-hub-grant-sync");
  });

  it("mounts fx-hub on the dashboard-api entrypoint", () => {
    expect(indexSrc.length, "entrypoint resolved to an empty string").toBeGreaterThan(0);
    const entry = code(indexSrc);
    expect(entry).toMatch(/from\s+["']\.\/fx-hub\/router["']/);
    expect(entry).toContain("createFxHubFetch");
    expect(entry).toContain("FX_HUB_PATHS");
  });
});
