/**
 * Pure helpers extracted in the single-route refactor — suggestions/theme/
 * accent seeding must not flash unconfigured defaults on first paint.
 */
import { describe, expect, it } from "vitest";
import { DEFAULT_CLIENT_CONFIG } from "./deploy-config";
import { DEFAULT_EMBED_TENANT_CONFIG } from "./embed-client-config";
import {
  resolveEmbedSeededTenant,
  resolveRouteClientConfig,
  toStockChatPrefsConfig,
} from "./route-client-config";

describe("resolveRouteClientConfig", () => {
  it("catalog mode returns the shared default client config", () => {
    expect(resolveRouteClientConfig({ mode: "catalog" })).toBe(DEFAULT_CLIENT_CONFIG);
  });

  it("product mode with null deployment still returns a client config", () => {
    const cfg = resolveRouteClientConfig({ mode: "product", deployment: null });
    expect(cfg.gate.webSearch).toBe(false);
  });
});

describe("resolveEmbedSeededTenant", () => {
  const base = { ...DEFAULT_EMBED_TENANT_CONFIG, slug: "occ" };

  it("parses JSON suggestion arrays and drops blank entries", () => {
    const { seeded } = resolveEmbedSeededTenant(base, {
      suggestions: JSON.stringify([" open tickets ", "", "who closed most"]),
    });
    expect(seeded.suggestions).toEqual([" open tickets ", "who closed most"]);
  });

  it("falls back to pipe-separated suggestions when JSON is invalid", () => {
    const { seeded } = resolveEmbedSeededTenant(base, {
      suggestions: "a| b | |c",
    });
    expect(seeded.suggestions).toEqual(["a", "b", "c"]);
  });

  it("ignores invalid accent colors and keeps tenant accent", () => {
    const withAccent = {
      ...base,
      accent: { color: "#112233", foreground: "#ffffff" },
    };
    const { seeded } = resolveEmbedSeededTenant(withAccent, {
      accent: "not-a-hex",
      accentForeground: "#000000",
    });
    expect(seeded.accent).toEqual(withAccent.accent);
  });

  it("applies welcome/placeholder only when present (no empty flash)", () => {
    const { seeded } = resolveEmbedSeededTenant(base, {
      welcome: "OCC help",
      placeholder: "Ask about tickets",
    });
    expect(seeded.welcome).toBe("OCC help");
    expect(seeded.placeholder).toBe("Ask about tickets");
  });

  it("parses a valid theme override without mutating the input tenant", () => {
    const before = structuredClone(base);
    const { seeded, urlTheme } = resolveEmbedSeededTenant(base, { theme: "light" });
    expect(urlTheme).toBe("light");
    expect(seeded.theme).toBe("light");
    expect(base).toEqual(before);
  });
});

describe("toStockChatPrefsConfig", () => {
  it("maps gate.webSearch onto tenantAllowsWeb", () => {
    const prefs = toStockChatPrefsConfig({
      ...DEFAULT_CLIENT_CONFIG,
      gate: { ...DEFAULT_CLIENT_CONFIG.gate, webSearch: true },
    });
    expect(prefs.tenantAllowsWeb).toBe(true);
  });

  it("allows the model picker when either allowPicker or features.modelPicker is set", () => {
    const viaAllow = toStockChatPrefsConfig({
      ...DEFAULT_CLIENT_CONFIG,
      models: { ...DEFAULT_CLIENT_CONFIG.models, allowPicker: true },
      features: { ...DEFAULT_CLIENT_CONFIG.features, modelPicker: false },
    });
    expect(viaAllow.allowModelPicker).toBe(true);

    const viaFeature = toStockChatPrefsConfig({
      ...DEFAULT_CLIENT_CONFIG,
      models: { ...DEFAULT_CLIENT_CONFIG.models, allowPicker: false },
      features: { ...DEFAULT_CLIENT_CONFIG.features, modelPicker: true },
    });
    expect(viaFeature.allowModelPicker).toBe(true);

    const neither = toStockChatPrefsConfig({
      ...DEFAULT_CLIENT_CONFIG,
      models: { ...DEFAULT_CLIENT_CONFIG.models, allowPicker: false },
      features: { ...DEFAULT_CLIENT_CONFIG.features, modelPicker: false },
    });
    expect(neither.allowModelPicker).toBe(false);
  });
});
