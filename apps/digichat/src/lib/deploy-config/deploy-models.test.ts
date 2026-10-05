import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { DEFAULT_CLIENT_CONFIG } from "./client-projection";
import { DEPLOY_DEFAULT_MODELS } from "./deploy-models";
import { loadDigichatConfig, resetDigichatConfigForTests } from "./loader";

// #5029: the unconfigured-container model table used to be a byte-identical
// block copied into loader.ts and client-projection.ts. Because the copies were
// equal, every value-equality test passed either way and the duplication was
// invisible — which is why it survived. These tests therefore assert the
// *structure*, not just the values: the table must have exactly one definition,
// in a config file, and neither consumer may name a model itself.

const CONFIG_FILE = resolve(__dirname, "../../../config/digichat-deploy-models.json");

/**
 * A quoted `provider/model` pair. Deliberately requires the first character to
 * be alphanumeric so relative imports ("./schema"), tsconfig aliases
 * ("@/lib/…") and absolute paths ("/app/config/…") never match — only real
 * provider model ids do.
 */
const MODEL_LITERAL = /"[a-z0-9][a-z0-9.-]*\/[a-z0-9][a-z0-9._-]*"/i;

const configJson = JSON.parse(readFileSync(CONFIG_FILE, "utf8")) as {
  default: string;
  available: string[];
};

describe("deploy model table has a single config source (#5029)", () => {
  it("keeps the default model and the allowed list in apps/digichat/config", () => {
    expect(configJson.default).toBe(DEPLOY_DEFAULT_MODELS.default);
    expect(configJson.available).toEqual(DEPLOY_DEFAULT_MODELS.available);
  });

  it("keeps `default` inside `available` so the picker can always select it", () => {
    expect(DEPLOY_DEFAULT_MODELS.available).toContain(DEPLOY_DEFAULT_MODELS.default);
  });

  it("lists no duplicate entries", () => {
    expect(DEPLOY_DEFAULT_MODELS.available).toEqual([
      ...new Set(DEPLOY_DEFAULT_MODELS.available),
    ]);
  });

  // The guard in deploy-models.ts runs at *import* time, so no assertion about
  // the good table can reach it: every other test in this file would still pass
  // if the `if` were deleted. This one imports the module against a bad table
  // and requires the throw. `doMock` rather than a hoisted `vi.mock` so the
  // already-imported good module above is unaffected.
  it("refuses to load a table whose default is not offered", async () => {
    vi.resetModules();
    vi.doMock(CONFIG_FILE, () => ({
      default: { default: "vendor/unoffered", available: ["vendor/other"] },
    }));
    try {
      await expect(import("./deploy-models")).rejects.toThrow(/is not in available/);
    } finally {
      vi.doUnmock(CONFIG_FILE);
      vi.resetModules();
    }
  });

  it("is non-empty — an empty table would silently strip every model", () => {
    expect(DEPLOY_DEFAULT_MODELS.available.length).toBeGreaterThan(0);
  });
});

describe("no consumer re-declares the deploy model table (#5029)", () => {
  // This is the load-bearing pair. Reverting either consumer to its own
  // inline literals fails here, and fails here ONLY — a value assertion
  // cannot distinguish the two states while the copies agree.
  for (const consumer of ["loader.ts", "client-projection.ts"]) {
    it(`${consumer} names no provider model id`, () => {
      const src = readFileSync(resolve(__dirname, consumer), "utf8");
      const found = src.match(new RegExp(MODEL_LITERAL.source, "gi")) ?? [];
      expect(found).toEqual([]);
    });

    it(`${consumer} reads the table from ./deploy-models`, () => {
      const src = readFileSync(resolve(__dirname, consumer), "utf8");
      expect(src).toMatch(/from "\.\/deploy-models"/);
    });
  }

  it("client-projection.ts does not import the server-only loader", () => {
    const src = readFileSync(resolve(__dirname, "client-projection.ts"), "utf8");
    expect(src).not.toMatch(/from "\.\/loader"/);
  });
});

describe("both consumers project the same config-sourced table (#5029)", () => {
  it("the unconfigured-container deployment default matches the config table", () => {
    resetDigichatConfigForTests();
    const cfg = loadDigichatConfig({ fileContents: null, env: {} });
    expect(cfg.deployment?.models).toEqual({
      ...DEPLOY_DEFAULT_MODELS,
      allowPicker: true,
    });
  });

  it("the browser-facing client config matches the config table", () => {
    expect(DEFAULT_CLIENT_CONFIG.models).toEqual({
      ...DEPLOY_DEFAULT_MODELS,
      allowPicker: true,
    });
  });

  it("the two projections agree — this is the pair that used to drift", () => {
    resetDigichatConfigForTests();
    const cfg = loadDigichatConfig({ fileContents: null, env: {} });
    expect(cfg.deployment?.models?.available).toEqual(DEFAULT_CLIENT_CONFIG.models.available);
    expect(cfg.deployment?.models?.default).toBe(DEFAULT_CLIENT_CONFIG.models.default);
  });
});
