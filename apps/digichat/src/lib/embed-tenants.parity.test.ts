import { describe, it, expect, afterEach, vi } from "vitest";
import { parseEmbedTenants, resetEmbedTenantRegistryForTests } from "./embed-tenants";
import { toEmbedClientConfig } from "./embed-client-config";
import { clientConfigFromEmbedTenant } from "./deploy-config/embed-bridge";
import { deploymentToEmbedTenant, embedTenantToDeployment } from "./deploy-config/loader";
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

// The /embed first paint does NOT use toEmbedClientConfig directly — it resolves
// the merged host deployment through embedTenantToDeployment and back out via
// deploymentToEmbedTenant (#4532). Covering only the projection missed that.
describe("embed tenant loader bridge parity (#4532)", () => {
  it("round-trips the feature flags and language through the deployment bridge", () => {
    const tenant = resolve({
      dictation: true,
      speech: true,
      sources: false,
      branchPicker: false,
      defaultLanguage: "nl",
    });
    const dep = embedTenantToDeployment(tenant);
    expect(dep.features.dictation).toBe(true);
    expect(dep.features.speech).toBe(true);
    expect(dep.features.sources).toBe(false);
    expect(dep.features.branchPicker).toBe(false);
    expect(dep.chrome.defaultLanguage).toBe("nl");

    const back = deploymentToEmbedTenant(dep);
    expect(back.dictation).toBe(true);
    expect(back.speech).toBe(true);
    expect(back.sources).toBe(false);
    expect(back.branchPicker).toBe(false);
    expect(back.defaultLanguage).toBe("nl");
  });

  it("keeps the app defaults through the deployment bridge when omitted", () => {
    const dep = embedTenantToDeployment(resolve({}));
    expect(dep.features.dictation).toBe(false);
    expect(dep.features.speech).toBe(false);
    expect(dep.features.sources).toBe(true);
    expect(dep.features.branchPicker).toBe(true);
    expect(dep.chrome.defaultLanguage).toBe(DEFAULT_LANGUAGE_CODE);
  });
});
