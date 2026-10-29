import { describe, expect, it } from "vitest";
import {
  BRAND_FONTS,
  BRAND_SKIN_CSS,
  BrandSkinSchema,
  brandSkinAttrs,
  brandSkinStyle,
  parseBrandSkin,
} from "./brand-skin";
import { parseEmbedTenants } from "./embed-tenants";
import { toEmbedClientConfig } from "./embed-client-config";
import { ChromeSchema } from "./deploy-config/schema";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import {
  deploymentToEmbedTenant,
  embedTenantToDeployment,
  materializeDigichatConfig,
} from "./deploy-config/loader";

const FULL = {
  fonts: { heading: "cabin", body: "mulish" },
  colors: { secondary: "#38848D", ink: "#2B2B2B", tint: "#FFEDDD" },
  shape: "pill",
} as const;

describe("tenant brand skin", () => {
  it("accepts a full brand and nothing outside the font registry or #rrggbb", () => {
    expect(parseBrandSkin(FULL, "t")).toEqual(FULL);
    expect(parseBrandSkin(undefined, "t")).toBeUndefined();
    expect(() => parseBrandSkin({ fonts: { body: "https://evil.example/font.woff2" } }, "t")).toThrow(
      /t: brand\.fonts\.body/,
    );
    expect(() => parseBrandSkin({ colors: { ink: "red" } }, "t")).toThrow(/brand\.colors\.ink/);
    expect(() => parseBrandSkin({ shape: "round" }, "t")).toThrow(/brand\.shape/);
    expect(() => parseBrandSkin({ logo: "x" }, "t")).toThrow();
  });

  it("maps fonts to the self-hosted next/font variables, never a URL", () => {
    const style = brandSkinStyle(FULL) as Record<string, string>;
    expect(style["--brand-heading-font"]).toContain(`var(${BRAND_FONTS.cabin})`);
    expect(style["--brand-body-font"]).toContain(`var(${BRAND_FONTS.mulish})`);
    expect(style["--brand-secondary"]).toBe("#38848D");
    expect(style["--brand-ink"]).toBe("#2B2B2B");
    expect(style["--brand-tint"]).toBe("#FFEDDD");
    expect(JSON.stringify(style)).not.toMatch(/https?:/);
  });

  it("emits only the attributes a field turns on, and nothing without a brand", () => {
    expect(brandSkinAttrs(FULL)).toEqual({
      "data-brand": "1",
      "data-brand-body": "1",
      "data-brand-heading": "1",
      "data-brand-ink": "1",
      "data-brand-tint": "1",
      "data-brand-secondary": "1",
      "data-brand-shape": "pill",
    });
    expect(brandSkinAttrs({ shape: "default" })).toEqual({ "data-brand": "1" });
    expect(brandSkinAttrs(null)).toBeUndefined();
    expect(brandSkinStyle(null)).toBeUndefined();
    expect(brandSkinStyle({})).toBeUndefined();
  });

  it("keeps every rule scoped under a data-brand attribute", () => {
    const selectors = BRAND_SKIN_CSS.split("}")
      .map((block) => block.split("{")[0]!.trim())
      .filter(Boolean)
      .flatMap((sel) => sel.split(/,(?![^(]*\))/).map((s) => s.trim()))
      .filter(Boolean);
    expect(selectors.length).toBeGreaterThan(10);
    for (const sel of selectors) {
      expect(sel, sel).toMatch(/^(\.(light|dark))?\[data-brand/);
    }
  });

  it("round-trips through the embed tenant row and the client projection", () => {
    const tenants = parseEmbedTenants(
      JSON.stringify({
        "brand.example.test": {
          slug: "brandtest",
          gateMode: "ungated",
          token: "fixture-token",
          backend: { type: "digigraph" },
          brand: FULL,
        },
      }),
    );
    const row = tenants.get("brand.example.test")!;
    expect(row.brand).toEqual(FULL);
    expect(toEmbedClientConfig(row).brand).toEqual(FULL);
  });

  it("refuses a bad brand on the tenant row like a bad accent", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "brand.example.test": {
            slug: "brandtest",
            gateMode: "ungated",
            token: "fixture-token",
            backend: { type: "digigraph" },
            brand: { colors: { tint: "#fff" } },
          },
        }),
      ),
    ).toThrow(/brand\.colors\.tint/);
  });

  it("is a chrome key in the deploy YAML schema", () => {
    expect(ChromeSchema.parse({ brand: FULL }).brand).toEqual(FULL);
    expect(BrandSkinSchema.safeParse({ fonts: { heading: "comic-sans" } }).success).toBe(false);
  });

  it("carries the brand from a deploy YAML to the tenant row and back", () => {
    const file = resolve(__dirname, "../../config/nomadis.yaml");
    const cfg = materializeDigichatConfig(loadYaml(readFileSync(file, "utf8")), "nomadis.yaml");
    const dep = Object.values(cfg.hosts ?? {})[0]!;
    expect(dep.chrome.brand).toEqual(FULL);
    const row = deploymentToEmbedTenant(dep);
    expect(row.brand).toEqual(FULL);
    expect(embedTenantToDeployment(row).chrome.brand).toEqual(FULL);
  });
});
