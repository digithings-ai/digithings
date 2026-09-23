import { describe, it, expect, afterEach, vi } from "vitest";
import { parseEmbedTenants, resetEmbedTenantRegistryForTests } from "./embed-tenants";
import { toEmbedClientConfig } from "./embed-client-config";
import { clientConfigFromEmbedTenant } from "./deploy-config/embed-bridge";
import { DEFAULT_LANGUAGE_CODE } from "./languages";

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
});

/** A minimal valid single-tenant registry with extra keys merged in. */
const entry = (keys: Record<string, unknown>) =>
  JSON.stringify({
    "example.com": {
      slug: "example",
      backend: { type: "digigraph" },
      gateMode: "turn_limited",
      token: "t",
      ...keys,
    },
  });

const resolve = (keys: Record<string, unknown>) =>
  parseEmbedTenants(entry(keys)).get("example.com")!;

const clientConfigFor = (keys: Record<string, unknown>) =>
  clientConfigFromEmbedTenant(toEmbedClientConfig(resolve(keys)));

describe("embed tenant app/embed config parity (#4532)", () => {
  it("carries dictation/speech/sources/branchPicker into the client features", () => {
    const cfg = clientConfigFor({
      dictation: true,
      speech: true,
      sources: false,
      branchPicker: false,
    });
    expect(cfg.features.dictation).toBe(true);
    expect(cfg.features.speech).toBe(true);
    // An explicit `false` must survive — it is the only way to turn these off.
    expect(cfg.features.sources).toBe(false);
    expect(cfg.features.branchPicker).toBe(false);
  });

  it("carries defaultLanguage into the client chrome", () => {
    expect(clientConfigFor({ defaultLanguage: "nl" }).chrome.defaultLanguage).toBe("nl");
  });

  it("keeps the app defaults when the tenant omits the feature keys", () => {
    const cfg = clientConfigFor({});
    expect(cfg.features.dictation).toBe(false);
    expect(cfg.features.speech).toBe(false);
    expect(cfg.features.sources).toBe(true);
    expect(cfg.features.branchPicker).toBe(true);
    expect(cfg.chrome.defaultLanguage).toBe(DEFAULT_LANGUAGE_CODE);
  });

  it("projects the new fields through toEmbedClientConfig", () => {
    const projected = toEmbedClientConfig(
      resolve({ dictation: true, sources: false, branchPicker: false, defaultLanguage: "fr" }),
    );
    expect(projected.dictation).toBe(true);
    expect(projected.sources).toBe(false);
    expect(projected.branchPicker).toBe(false);
    expect(projected.defaultLanguage).toBe("fr");
  });

  it("rejects a non-boolean feature flag", () => {
    expect(() => parseEmbedTenants(entry({ dictation: "yes" }))).toThrow(/dictation/);
    expect(() => parseEmbedTenants(entry({ sources: 1 }))).toThrow(/sources/);
  });

  it("rejects an unknown defaultLanguage", () => {
    expect(() => parseEmbedTenants(entry({ defaultLanguage: "klingon" }))).toThrow(
      /defaultLanguage/,
    );
  });
});
