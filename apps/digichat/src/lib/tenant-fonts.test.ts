import { describe, expect, it } from "vitest";

import { hasTenantHeadingRule, parseTenantFonts, tenantFontStyle, tenantHeadingFontCss, TENANT_FONTS } from "./tenant-fonts";

describe("tenant fonts", () => {
  it("is absent when the tenant sets none", () => {
    expect(parseTenantFonts(undefined, "t")).toBeUndefined();
    expect(tenantFontStyle(null)).toBeUndefined();
    expect(tenantFontStyle({})).toBeUndefined();
  });

  it("accepts only allowlisted faces", () => {
    expect(parseTenantFonts({ heading: "cabin", body: "mulish" }, "t")).toEqual({
      heading: "cabin",
      body: "mulish",
    });
    expect(() => parseTenantFonts({ body: "https://evil.example/f.woff2" }, "t")).toThrow(/fonts\.body/);
    expect(() => parseTenantFonts({ body: "mulish", size: 3 }, "t")).toThrow();
  });

  it("emits font properties only", () => {
    const style = tenantFontStyle({ heading: "cabin", body: "mulish" }) as Record<string, string>;
    expect(Object.keys(style).every((k) => k.startsWith("--font-") || k === "fontFamily")).toBe(true);
    expect(style.fontFamily).toBe("var(--font-sans)");
    expect(style["--font-sans"]).toContain(`var(${TENANT_FONTS.mulish})`);
    expect(style["--font-heading"]).toContain(`var(${TENANT_FONTS.cabin})`);
  });

  it("accepts a heading weight from the four shipped steps only", () => {
    expect(parseTenantFonts({ headingWeight: 700 }, "t")).toEqual({ headingWeight: 700 });
    expect(() => parseTenantFonts({ headingWeight: 650 }, "t")).toThrow(/fonts\.headingWeight/);
    expect(() => parseTenantFonts({ headingWeight: "700" }, "t")).toThrow(/fonts\.headingWeight/);
  });

  it("adds the heading rule only for a heading face or weight", () => {
    expect(hasTenantHeadingRule(null)).toBe(false);
    expect(hasTenantHeadingRule({ body: "mulish" })).toBe(false);
    expect(tenantHeadingFontCss({ body: "mulish" })).toBe("");
    expect(tenantHeadingFontCss({ heading: "cabin" })).toMatch(/\{font-family:var\(--font-heading\)\}$/);
    expect(tenantHeadingFontCss({ headingWeight: 600 })).toMatch(/\{font-weight:600\}$/);
    const both = tenantHeadingFontCss({ heading: "cabin", headingWeight: 700 });
    expect(both.startsWith("[data-tenant-heading-font] :is(.aui-thread-welcome-message-inner,")).toBe(true);
    expect(both).toMatch(/\{font-family:var\(--font-heading\);font-weight:700\}$/);
  });

  it("keeps the weight out of the wrapper's inline font style", () => {
    expect(tenantFontStyle({ headingWeight: 700 })).toBeUndefined();
  });
});
