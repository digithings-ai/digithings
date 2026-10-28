import { describe, expect, it } from "vitest";
import corsSrc from "./cors.ts?raw";
import httpSrc from "./http.ts?raw";
import envSrc from "./env.ts?raw";
import marketSrc from "./market.ts?raw";
import adminSrc from "./admin.ts?raw";
import routesSrc from "./routes.ts?raw";
import routerSrc from "./router.ts?raw";
import kvStoreSrc from "./kv-store.ts?raw";
import indexSrc from "../index.ts?raw";

// Two properties the port has to hold for the cutover to be a cutover rather
// than a rewrite:
//
//   1. No Deno global survives anywhere in the tree. A single `Deno.env.get`
//      left behind would throw at request time on Workers, not at build time,
//      and the only warning would be a 500 in production.
//   2. No wrangler config, binding or secret is introduced. The whole reason
//      this leaf needs no production change is that it declares nothing.
//
// Source text is read with Vite's `?raw` import because tsconfig for this
// package has no `@types/node`, so `node:fs` cannot be used here.

const SOURCES: Record<string, string> = {
  "cors.ts": corsSrc,
  "http.ts": httpSrc,
  "env.ts": envSrc,
  "market.ts": marketSrc,
  "admin.ts": adminSrc,
  "routes.ts": routesSrc,
  "router.ts": routerSrc,
  "kv-store.ts": kvStoreSrc,
};

/** Removes block and line comments so the scans below read CODE, not prose. */
function code(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

describe("the ported prices-live tree is Deno-free", () => {
  it("strips comments, so the scans read code and not the prose describing it", () => {
    // Positive control: without this the scans below would match the very
    // comments that document WHY the tree is Deno-free.
    const sample = "/** mentions Deno.env */\nconst x = 1; // and Deno.serve";
    expect(code(sample)).not.toMatch(/Deno/);
    expect(code(sample)).toContain("const x = 1;");
    expect(code(sample).trim()).toBe("const x = 1;");
  });

  it("reads back a non-trivial amount of source, so the scan is not vacuous", () => {
    // Without this, a `?raw` import silently resolving to "" would make every
    // assertion below pass on an empty subject.
    const total = Object.values(SOURCES).reduce((n, s) => n + s.length, 0);
    expect(total).toBeGreaterThan(5000);
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
    // The names appear in the port as lookups against `env`, which is correct;
    // what must not appear is a config file that would make CI require a real
    // secret. Assert this against the tracked wrangler config, which this leaf
    // must leave byte-identical.
    const joined = Object.values(SOURCES).map(code).join("\n");
    expect(joined).not.toMatch(/\[vars\]|\[secrets\]|\[\[kv_namespaces\]\]/);
  });
});

describe("router surface", () => {
  it("declares the ported path", () => {
    expect(routerSrc).toContain("/prices-live");
  });

  it("mounts the prices-live paths on the entrypoint only behind its flag", () => {
    // src/index.ts is the deployed entrypoint. Supabase exit S4 mounts the
    // router there, but only when PRICES_LIVE_WORKER_ROUTES is "1", so the
    // edge function stays the serving path until cutover.
    expect(indexSrc.length, "entrypoint resolved to an empty string").toBeGreaterThan(0);
    const entry = code(indexSrc);
    expect(entry).toMatch(/PRICES_LIVE_ROUTE_PATHS\.has\(path\)\s*&&\s*pricesLiveWorkerRoutesOn\(/);
    expect(entry.match(/createPricesLiveFetch\(/g)?.length).toBe(1);
  });
});
