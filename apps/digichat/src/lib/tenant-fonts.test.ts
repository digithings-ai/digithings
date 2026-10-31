import { describe, expect, it } from "vitest";

import { parseTenantFonts, tenantFontStyle, tenantOverlayFontCss, TENANT_FONTS } from "./tenant-fonts";

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
});

describe("tenant overlay font", () => {
  it("is empty without a body face", () => {
    expect(tenantOverlayFontCss(null)).toBe("");
    expect(tenantOverlayFontCss({ heading: "cabin" })).toBe("");
  });

  it("gives portaled tooltips, popovers and dialogs the body face, outside the digichat skin", () => {
    const css = tenantOverlayFontCss({ heading: "cabin", body: "mulish" });
    expect(css).toContain('html:not(:has([data-thread-skin="digichat"]))');
    for (const slot of ["tooltip-content", "popover-content", "dialog-content", "dropdown-menu-content"]) {
      expect(css).toContain(`[data-slot=${slot}]`);
    }
    expect(css).toContain(`font-family:var(${TENANT_FONTS.mulish})`);
    expect(css).not.toMatch(/url\(|color|background/);
  });
});
